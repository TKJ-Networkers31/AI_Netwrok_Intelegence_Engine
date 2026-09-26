from __future__ import annotations

import asyncio

import pytest

from app.events.bus import Event, EventBus


@pytest.mark.asyncio
async def test_publish_calls_sync_subscriber():
    bus = EventBus()
    received = []

    bus.subscribe("test.event", lambda event: received.append(event.payload))

    await bus.publish(Event(name="test.event", payload={"x": 1}))

    assert received == [{"x": 1}]


@pytest.mark.asyncio
async def test_publish_calls_async_subscriber():
    bus = EventBus()
    received = []

    async def handler(event: Event) -> None:
        await asyncio.sleep(0)
        received.append(event.payload)

    bus.subscribe("test.event", handler)

    await bus.publish(Event(name="test.event", payload={"x": 2}))

    assert received == [{"x": 2}]


@pytest.mark.asyncio
async def test_publish_only_calls_matching_subscribers():
    bus = EventBus()
    received = []

    bus.subscribe("event.a", lambda event: received.append("a"))
    bus.subscribe("event.b", lambda event: received.append("b"))

    await bus.publish(Event(name="event.a"))

    assert received == ["a"]


@pytest.mark.asyncio
async def test_unsubscribe_removes_handler():
    bus = EventBus()
    received = []

    def handler(event: Event) -> None:
        received.append(event.payload)

    bus.subscribe("test.event", handler)
    bus.unsubscribe("test.event", handler)

    await bus.publish(Event(name="test.event", payload={}))

    assert received == []


def test_publish_sync_runs_handlers():
    bus = EventBus()
    received = []

    bus.subscribe("test.event", lambda event: received.append(event.payload))

    bus.publish_sync(Event(name="test.event", payload={"y": 3}))

    assert received == [{"y": 3}]


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_does_not_raise():
    bus = EventBus()

    await bus.publish(Event(name="nothing.subscribed"))
