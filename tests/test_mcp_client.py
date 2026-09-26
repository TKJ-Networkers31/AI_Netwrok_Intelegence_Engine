from __future__ import annotations

from typing import Any, Optional

import pytest

from app.mcp.client import MCPClient
from app.mcp.errors import (
    MCPConnectionError,
    MCPDisconnectedError,
    MCPMalformedResponseError,
    MCPNotConnectedError,
    MCPTimeoutError,
)
from app.mcp.transport import Transport


class FakeTransport(Transport):
    """An in-memory `Transport` double: `responses` is a queue of canned
    responses (or exceptions to raise) returned in order from `receive()`.
    """

    def __init__(self, responses: Optional[list[Any]] = None):
        self.responses = list(responses or [])
        self.sent: list[dict[str, Any]] = []
        self.connected = False
        self.connect_error: Optional[Exception] = None
        self.send_error: Optional[Exception] = None

    def connect(self) -> None:
        if self.connect_error:
            raise self.connect_error
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def send(self, message: dict[str, Any]) -> None:
        if self.send_error:
            raise self.send_error
        self.sent.append(message)

    def receive(self, timeout: float) -> Optional[dict[str, Any]]:
        if not self.responses:
            raise TimeoutError("no more canned responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def is_connected(self) -> bool:
        return self.connected


def test_connect_and_disconnect():
    transport = FakeTransport()
    client = MCPClient(transport, name="test")

    client.connect()
    assert client.is_connected is True

    client.disconnect()
    assert client.is_connected is False


def test_connect_failure_raises_mcp_connection_error():
    transport = FakeTransport()
    transport.connect_error = OSError("boom")
    client = MCPClient(transport, name="test")

    with pytest.raises(MCPConnectionError):
        client.connect()


def test_invoke_before_connect_raises_not_connected():
    client = MCPClient(FakeTransport(), name="test")

    with pytest.raises(MCPNotConnectedError):
        client.invoke_tool("ping", {})


def test_discover_tools_parses_schemas():
    transport = FakeTransport(
        responses=[
            {
                "id": "req-1",
                "success": True,
                "result": {
                    "tools": [
                        {
                            "name": "ping",
                            "description": "ping a host",
                            "input_schema": {"type": "object"},
                            "output_schema": {"type": "object"},
                        }
                    ]
                },
            }
        ]
    )
    client = MCPClient(transport, name="test")
    client.connect()

    tools = client.discover_tools()

    assert len(tools) == 1
    assert tools[0].name == "ping"
    assert tools[0].description == "ping a host"
    # Cached on second call without hitting the transport again.
    tools_again = client.discover_tools()
    assert tools_again == tools


def test_discover_tools_malformed_raises():
    transport = FakeTransport(responses=[{"id": "req-1", "success": False, "error": {"code": "x"}}])
    client = MCPClient(transport, name="test")
    client.connect()

    with pytest.raises(MCPMalformedResponseError):
        client.discover_tools()


def test_invoke_tool_success():
    transport = FakeTransport(
        responses=[{"id": "req-1", "success": True, "result": {"reachable": True}}]
    )
    client = MCPClient(transport, name="test")
    client.connect()

    response = client.invoke_tool("tcp_connectivity", {"host": "10.0.0.1", "port": 22})

    assert response.success is True
    assert response.result == {"reachable": True}
    assert transport.sent[0]["method"] == "invoke"
    assert transport.sent[0]["params"] == {"tool": "tcp_connectivity", "arguments": {"host": "10.0.0.1", "port": 22}}


def test_invoke_tool_error_response():
    transport = FakeTransport(
        responses=[
            {"id": "req-1", "success": False, "error": {"code": "connection_failed", "message": "no route"}}
        ]
    )
    client = MCPClient(transport, name="test")
    client.connect()

    response = client.invoke_tool("ping", {"host": "10.0.0.1"})

    assert response.success is False
    assert response.error["code"] == "connection_failed"


def test_invoke_tool_timeout_raises():
    transport = FakeTransport(responses=[TimeoutError("slow")])
    client = MCPClient(transport, name="test")
    client.connect()

    with pytest.raises(MCPTimeoutError):
        client.invoke_tool("ping", {"host": "10.0.0.1"})


def test_invoke_tool_disconnect_raises():
    transport = FakeTransport(responses=[None])
    client = MCPClient(transport, name="test")
    client.connect()

    with pytest.raises(MCPDisconnectedError):
        client.invoke_tool("ping", {"host": "10.0.0.1"})
    assert client.is_connected is False


def test_invoke_tool_malformed_response_raises():
    transport = FakeTransport(responses=[{"not": "a valid response"}])
    client = MCPClient(transport, name="test")
    client.connect()

    with pytest.raises(MCPMalformedResponseError):
        client.invoke_tool("ping", {"host": "10.0.0.1"})


def test_send_failure_raises_connection_error_and_disconnects():
    transport = FakeTransport()
    client = MCPClient(transport, name="test")
    client.connect()
    transport.send_error = BrokenPipeError("pipe closed")

    with pytest.raises(MCPConnectionError):
        client.invoke_tool("ping", {"host": "10.0.0.1"})
    assert client.is_connected is False


def test_context_manager_connects_and_disconnects():
    transport = FakeTransport()
    with MCPClient(transport, name="test") as client:
        assert client.is_connected is True
    assert transport.connected is False
