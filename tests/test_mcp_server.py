from __future__ import annotations

import io
import json
from typing import Any

from app.mcp.protocol import ToolSchema
from app.mcp.server import MCPServer


class FakeHandler:
    def __init__(self, tools=None, invoke_results=None, raise_on_invoke=False):
        self._tools = tools or []
        self._invoke_results = invoke_results or {}
        self._raise_on_invoke = raise_on_invoke
        self.invocations: list[tuple[str, dict]] = []

    def list_tools(self) -> list[ToolSchema]:
        return self._tools

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.invocations.append((name, arguments))
        if self._raise_on_invoke:
            raise RuntimeError("handler exploded")
        return self._invoke_results.get(name, {"success": True, "data": {}})


def _server(handler) -> tuple[MCPServer, io.StringIO]:
    output = io.StringIO()
    server = MCPServer(handler, input_stream=io.StringIO(""), output_stream=output)
    return server, output


def _last_response(output: io.StringIO) -> dict:
    lines = [line for line in output.getvalue().splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_ping_method():
    server, output = _server(FakeHandler())

    server.handle_request({"id": "1", "method": "ping", "params": {}})

    response = _last_response(output)
    assert response == {"id": "1", "success": True, "result": {"pong": True}}


def test_discover_returns_tool_schemas():
    tool = ToolSchema(name="ping", description="ping a host", input_schema={"type": "object"})
    server, output = _server(FakeHandler(tools=[tool]))

    server.handle_request({"id": "1", "method": "discover", "params": {}})

    response = _last_response(output)
    assert response["success"] is True
    assert response["result"]["tools"] == [
        {"name": "ping", "description": "ping a host", "input_schema": {"type": "object"}, "output_schema": {}}
    ]


def test_invoke_success():
    handler = FakeHandler(invoke_results={"ping": {"success": True, "data": {"reachable": True}}})
    server, output = _server(handler)

    server.handle_request({"id": "1", "method": "invoke", "params": {"tool": "ping", "arguments": {"host": "x"}}})

    response = _last_response(output)
    assert response == {"id": "1", "success": True, "result": {"reachable": True}}
    assert handler.invocations == [("ping", {"host": "x"})]


def test_invoke_error_result():
    handler = FakeHandler(
        invoke_results={
            "ping": {"success": False, "error": {"code": "connection_failed", "message": "no route"}}
        }
    )
    server, output = _server(handler)

    server.handle_request({"id": "1", "method": "invoke", "params": {"tool": "ping", "arguments": {}}})

    response = _last_response(output)
    assert response["success"] is False
    assert response["error"]["code"] == "connection_failed"


def test_invoke_missing_tool_name():
    server, output = _server(FakeHandler())

    server.handle_request({"id": "1", "method": "invoke", "params": {}})

    response = _last_response(output)
    assert response["success"] is False
    assert response["error"]["code"] == "invalid_request"


def test_invoke_handler_exception_becomes_structured_error():
    server, output = _server(FakeHandler(raise_on_invoke=True))

    server.handle_request({"id": "1", "method": "invoke", "params": {"tool": "ping", "arguments": {}}})

    response = _last_response(output)
    assert response["success"] is False
    assert response["error"]["code"] == "tool_execution_failed"


def test_unknown_method():
    server, output = _server(FakeHandler())

    server.handle_request({"id": "1", "method": "not_a_real_method", "params": {}})

    response = _last_response(output)
    assert response["success"] is False
    assert response["error"]["code"] == "unknown_method"


def test_handle_line_malformed_json():
    server, output = _server(FakeHandler())

    server.handle_line("this is not json")

    response = _last_response(output)
    assert response["success"] is False
    assert response["error"]["code"] == "malformed_request"


def test_handle_line_ignores_blank_lines():
    server, output = _server(FakeHandler())

    server.handle_line("   ")

    assert output.getvalue() == ""


def test_serve_forever_processes_each_line():
    handler = FakeHandler(invoke_results={"ping": {"success": True, "data": {}}})
    input_stream = io.StringIO(
        json.dumps({"id": "1", "method": "ping", "params": {}})
        + "\n"
        + json.dumps({"id": "2", "method": "invoke", "params": {"tool": "ping", "arguments": {}}})
        + "\n"
    )
    output = io.StringIO()
    server = MCPServer(handler, input_stream=input_stream, output_stream=output)

    server.serve_forever()

    lines = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["id"] == "1"
    assert lines[1]["id"] == "2"
