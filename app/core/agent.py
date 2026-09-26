"""ANIE Agent core.

The Agent is the single entry point used by callers (CLI, and later other
interfaces). It knows nothing about specific providers — it only talks to
the ModelRouter/ModelProvider abstraction, the EventBus, and (Phase 2) an
optional CapabilityExecutor.

Phase 1 added automatic fallback: if the primary provider's `generate()`
call fails with a recoverable (runtime/provider) error, and the router has
a fallback provider configured, the Agent retries the same Context against
the fallback provider before giving up.

Phase 2 adds a bounded tool-calling loop on top of that: if a provider
returns `ExecutionResult.tool_call_requested(...)` (because the model asked
to invoke one or more tools) and a `CapabilityExecutor` was supplied, the
Agent executes each requested tool through the execution boundary
(allowlist -> schema validation -> permission/risk check -> MCP invocation),
appends the (structured, JSON-serialized) result back into the Context as a
tool message, and calls the provider again. This repeats up to
`max_tool_iterations` times, after which the Agent gives up with a
structured `TOOL_EXECUTION_FAILED` error rather than looping forever — this
is deliberately NOT autonomous multi-step reasoning/planning, just a small,
bounded "ask -> tool -> ask again" loop.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Optional

from app.core.types import Context, ErrorCode, ExecutionResult
from app.events.bus import Event, EventBus
from app.models.router import ModelRouter

if TYPE_CHECKING:
    from app.capabilities.executor import CapabilityExecutor

logger = logging.getLogger("anie.agent")

DEFAULT_SYSTEM_PROMPT = (
    "You are ANIE, a network engineering assistant. Be precise and concise."
)

DEFAULT_MAX_TOOL_ITERATIONS = 3

# Error codes that indicate a configuration/programming problem rather than
# a runtime provider failure. Falling back to a second provider would not
# help with these, so the Agent never retries on them.
_NON_RECOVERABLE_CODES = {
    ErrorCode.INVALID_CONFIGURATION,
    ErrorCode.INVALID_PROVIDER,
}


class Agent:
    """Minimal ANIE agent loop.

    input -> Context -> ModelRouter -> Provider.generate() -> ExecutionResult
                                  (-> Fallback Provider.generate() on failure)
                                  (-> CapabilityExecutor.execute() on tool_calls,
                                      then Provider.generate() again)
    """

    def __init__(
        self,
        router: ModelRouter,
        event_bus: Optional[EventBus] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tool_executor: Optional["CapabilityExecutor"] = None,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    ):
        self.router = router
        self.event_bus = event_bus or EventBus()
        self.system_prompt = system_prompt
        self.tool_executor = tool_executor
        self.max_tool_iterations = max_tool_iterations

    def run(self, user_input: str) -> ExecutionResult:
        """Run a single, stateless request through the agent loop."""
        request_id = str(uuid.uuid4())

        logger.info(
            "agent.request",
            extra={"component": "agent", "event": "agent.request", "request_id": request_id},
        )
        self.event_bus.publish_sync(
            Event(name="agent.request", payload={"input": user_input, "request_id": request_id})
        )

        context = self._build_context(user_input)
        result = self._generate_with_fallback(context, request_id)
        result = self._run_tool_loop(context, result, request_id)

        result.metadata.setdefault("request_id", request_id)
        if result.success:
            self.event_bus.publish_sync(
                Event(
                    name="agent.response",
                    payload={
                        "response": result.response,
                        "request_id": request_id,
                        "used_fallback": result.metadata.get("used_fallback", False),
                    },
                )
            )
        else:
            self.event_bus.publish_sync(
                Event(name="agent.error", payload={"error": result.error, "request_id": request_id})
            )
        return result

    def _generate_with_fallback(self, context: Context, request_id: str) -> ExecutionResult:
        """Call the primary provider, falling back to the configured
        fallback provider (if any) on a recoverable failure. Identical in
        spirit to Phase 1's inline logic, just factored out so the Phase 2
        tool loop can call it again for each additional turn.
        """
        provider = self.router.get_provider()
        result = provider.generate(context)

        if result.success:
            return result

        primary_error = result.error
        logger.error(
            "model.error",
            extra={"component": "agent", "event": "model.error", "request_id": request_id},
        )

        fallback_provider = self._get_fallback_provider()
        should_attempt_fallback = (
            fallback_provider is not None
            and primary_error is not None
            and primary_error.code not in _NON_RECOVERABLE_CODES
        )

        if not should_attempt_fallback:
            return result

        logger.info(
            "agent.fallback",
            extra={"component": "agent", "event": "agent.fallback", "request_id": request_id},
        )
        self.event_bus.publish_sync(
            Event(
                name="agent.fallback",
                payload={"primary_error": primary_error, "request_id": request_id},
            )
        )

        fallback_result = fallback_provider.generate(context)

        if fallback_result.success:
            fallback_result.metadata["used_fallback"] = True
            fallback_result.metadata["primary_error_code"] = primary_error.code.value
            return fallback_result

        combined = ExecutionResult.fail(
            ErrorCode.ALL_PROVIDERS_FAILED,
            "Both the primary and fallback providers failed. "
            f"primary=[{primary_error.code.value}] {primary_error.message} | "
            f"fallback=[{fallback_result.error.code.value}] {fallback_result.error.message}",
            details={
                "primary_error": {
                    "code": primary_error.code.value,
                    "message": primary_error.message,
                },
                "fallback_error": {
                    "code": fallback_result.error.code.value,
                    "message": fallback_result.error.message,
                },
            },
        )

        logger.error(
            "agent.error",
            extra={"component": "agent", "event": "agent.error", "request_id": request_id},
        )
        return combined

    def _run_tool_loop(
        self, context: Context, result: ExecutionResult, request_id: str
    ) -> ExecutionResult:
        """If the model requested tool calls (and a `tool_executor` is
        configured), execute them through the capability execution
        boundary, feed the results back into the Context, and re-prompt the
        model — up to `max_tool_iterations` times.
        """
        if self.tool_executor is None:
            return result

        iterations = 0
        while result.success and result.tool_calls and iterations < self.max_tool_iterations:
            iterations += 1
            context.add_assistant_tool_calls(result.tool_calls)

            for tool_call in result.tool_calls:
                tool_result = self.tool_executor.execute(tool_call.name, tool_call.arguments)
                logger.info(
                    "tool.invoke",
                    extra={"component": "agent", "event": "tool.invoke", "request_id": request_id},
                )
                self.event_bus.publish_sync(
                    Event(
                        name="tool.invoke",
                        payload={
                            "tool": tool_call.name,
                            "success": tool_result.success,
                            "request_id": request_id,
                        },
                    )
                )
                context.add_tool_result(
                    tool_call.id, tool_call.name, json.dumps(tool_result.to_dict())
                )

            result = self._generate_with_fallback(context, request_id)

        if result.success and result.tool_calls and iterations >= self.max_tool_iterations:
            logger.error(
                "agent.error",
                extra={"component": "agent", "event": "agent.error", "request_id": request_id},
            )
            return ExecutionResult.fail(
                ErrorCode.TOOL_EXECUTION_FAILED,
                f"Exceeded the maximum number of tool-call iterations "
                f"({self.max_tool_iterations}) without producing a final response.",
            )

        return result

    def _get_fallback_provider(self):
        """Return the router's fallback provider, if any.

        Uses getattr defensively so any router implementation that predates
        `get_fallback_provider()` (e.g. a Phase 0 test double) still works
        exactly as before — it's simply treated as "no fallback configured".
        """
        getter = getattr(self.router, "get_fallback_provider", None)
        if getter is None:
            return None
        return getter()

    def _build_context(self, user_input: str) -> Context:
        context = Context(system_prompt=self.system_prompt)
        if self.tool_executor is not None:
            context.tools = self.tool_executor.get_tool_definitions()
        context.add_user_message(user_input)
        return context
