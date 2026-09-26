"""ANIE Agent core.

The Agent is the single entry point used by callers (CLI, and later other
interfaces). It knows nothing about specific providers — it only talks to
the ModelRouter/ModelProvider abstraction and the EventBus.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.core.types import Context, ExecutionResult
from app.events.bus import Event, EventBus
from app.models.router import ModelRouter

logger = logging.getLogger("anie.agent")

DEFAULT_SYSTEM_PROMPT = (
    "You are ANIE, a network engineering assistant. Be precise and concise."
)


class Agent:
    """Minimal ANIE agent loop.

    input -> Context -> ModelRouter -> Provider.generate() -> ExecutionResult
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
        else:
            logger.error(
                "model.error",
                extra={
                    "component": "agent",
                    "event": "model.error",
                    "request_id": request_id,
                },
            )
            self.event_bus.publish_sync(
                Event(
                    name="agent.error",
                    payload={"error": result.error, "request_id": request_id},
                )
            )

        result.metadata.setdefault("request_id", request_id)
        return result

    def _build_context(self, user_input: str) -> Context:
        context = Context(system_prompt=self.system_prompt)
        context.add_user_message(user_input)
        return context
