"""Minimal event bus foundation.

Phase 0 scope: publish/subscribe only. No automation rules, no persistence,
no complex event routing — those belong to later phases.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Union

Handler = Union[Callable[["Event"], None], Callable[["Event"], Awaitable[None]]]


@dataclass
class Event:
    """A simple, typed event representation."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """A minimal, asynchronous-safe publish/subscribe event bus.

    Subscribers may be plain sync callables or async callables (coroutine
    functions); both are supported. `publish` is async so handlers are
    awaited in a predictable order, and `publish_sync` is provided as a
    convenience wrapper for non-async call sites (e.g. the CLI).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}

    def subscribe(self, event_name: str, handler: Handler) -> None:
        self._subscribers.setdefault(event_name, []).append(handler)

    def unsubscribe(self, event_name: str, handler: Handler) -> None:
        handlers = self._subscribers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        for handler in list(self._subscribers.get(event.name, [])):
            result = handler(event)
            if inspect.isawaitable(result):
                await result

    def publish_sync(self, event: Event) -> None:
        """Publish an event from synchronous code.

        Runs the async `publish` to completion via `asyncio.run`. Must not be
        called from within a running event loop; use `await publish(...)`
        directly in that case.
        """
        asyncio.run(self.publish(event))
