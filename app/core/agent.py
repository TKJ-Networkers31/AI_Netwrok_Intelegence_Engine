"""ANIE Agent core.

The Agent is the single entry point used by callers (CLI, and later other
interfaces). It knows nothing about specific providers — it only talks to
the ModelRouter/ModelProvider abstraction and the EventBus.

Phase 1 adds automatic fallback: if the primary provider's `generate()`
call fails with a recoverable (runtime/provider) error, and the router has
a fallback provider configured, the Agent retries the same Context against
the fallback provider before giving up. It does NOT fall back for
configuration/programming errors (those never reach this point — they
raise during Config/ModelRouter construction) or for the small set of
ErrorCodes that represent invalid configuration/provider rather than a
runtime failure.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.core.types import ErrorCode, ExecutionResult, Context
from app.events.bus import Event, EventBus
from app.models.router import ModelRouter

logger = logging.getLogger("anie.agent")

DEFAULT_SYSTEM_PROMPT = (
    "You are ANIE, a network engineering assistant. Be precise and concise."
)

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
    """

    def __init__(
        self,
        router: ModelRouter,
        event_bus: Optional[EventBus] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ):
        self.router = router
        self.event_bus = event_bus or EventBus()
        self.system_prompt = system_prompt

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
        provider = self.router.get_provider()
        result = provider.generate(context)

        if result.success:
            self.event_bus.publish_sync(
                Event(
                    name="agent.response",
                    payload={"response": result.response, "request_id": request_id},
                )
            )
            result.metadata.setdefault("request_id", request_id)
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
            self.event_bus.publish_sync(
                Event(name="agent.error", payload={"error": result.error, "request_id": request_id})
            )
            result.metadata.setdefault("request_id", request_id)
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
            fallback_result.metadata.setdefault("request_id", request_id)
            self.event_bus.publish_sync(
                Event(
                    name="agent.response",
                    payload={
                        "response": fallback_result.response,
                        "request_id": request_id,
                        "used_fallback": True,
                    },
                )
            )
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
        combined.metadata.setdefault("request_id", request_id)

        logger.error(
            "agent.error",
            extra={"component": "agent", "event": "agent.error", "request_id": request_id},
        )
        self.event_bus.publish_sync(
            Event(name="agent.error", payload={"error": combined.error, "request_id": request_id})
        )
        return combined

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
        context.add_user_message(user_input)
        return context
