"""Minimal MCP server loop.

Reads newline-delimited JSON requests from an input stream, dispatches them
to a `ToolHandler` (`list_tools` / `invoke`), and writes newline-delimited
JSON responses to an output stream — the exact framing
`app.mcp.transport.StdioTransport` expects on the other end.

This loop is transport-agnostic in the same spirit as the client: it
doesn't know or care whether its input/output streams are wired to a pipe,
a socket, or a test double (`io.StringIO`) — it's handed file-like objects.
Vendor logic (talking to RouterOS, running `ping`, etc.) lives entirely in
`app.adapters`; this module only implements the protocol envelope.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Protocol, TextIO

from app.mcp.protocol import ToolSchema


class ToolHandler(Protocol):
    """What `MCPServer` needs from whatever backs it — in practice an
    `app.mcp.adapter_handler.AdapterToolHandler` wrapping an `Adapter`."""

    def list_tools(self) -> list[ToolSchema]: ...

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return `{"success": True, "data": {...}}` or
        `{"success": False, "error": {"code": ..., "message": ...}}`."""
        ...


class MCPServer:
    def __init__(
        self,
        handler: ToolHandler,
        input_stream: TextIO = sys.stdin,
        output_stream: TextIO = sys.stdout,
    ):
        self._handler = handler
        self._input_stream = input_stream
        self._output_stream = output_stream

    def serve_forever(self) -> None:
        """Block, handling one newline-delimited JSON request per line,
        until the input stream is closed."""
        for line in self._input_stream:
            self.handle_line(line)

    def handle_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            self._write_error(None, "malformed_request", "Request was not valid JSON.")
            return
        self.handle_request(request)

    def handle_request(self, request: dict[str, Any]) -> None:
        if not isinstance(request, dict):
            self._write_error(None, "malformed_request", "Request must be a JSON object.")
            return

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        if method == "ping":
            self._write_success(request_id, {"pong": True})
            return

        if method == "discover":
            self._handle_discover(request_id)
            return

        if method == "invoke":
            self._handle_invoke(request_id, params)
            return

        self._write_error(request_id, "unknown_method", f"Unknown method: {method!r}")

    def _handle_discover(self, request_id: Any) -> None:
        tools: list[ToolSchema] = self._handler.list_tools()
        self._write_success(
            request_id,
            {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "output_schema": tool.output_schema,
                    }
                    for tool in tools
                ]
            },
        )

    def _handle_invoke(self, request_id: Any, params: dict[str, Any]) -> None:
        name = params.get("tool")
        arguments = params.get("arguments") or {}
        if not name:
            self._write_error(request_id, "invalid_request", "'tool' is required for invoke.")
            return

        try:
            result = self._handler.invoke(name, arguments)
        except Exception as exc:
            # Defensive: the Adapter/ToolHandler contract says "never
            # raise", but a server process must not crash (and drop every
            # in-flight request) if that contract is violated somewhere.
            self._write_error(request_id, "tool_execution_failed", str(exc))
            return

        if result.get("success"):
            self._write_success(request_id, result.get("data", {}))
            return

        error = result.get("error") or {"code": "unknown_error", "message": "Tool invocation failed."}
        self._write_error(request_id, error.get("code", "unknown_error"), error.get("message", ""))

    def _write_success(self, request_id: Any, result: dict[str, Any]) -> None:
        self._write({"id": request_id, "success": True, "result": result})

    def _write_error(self, request_id: Any, code: str, message: str) -> None:
        self._write({"id": request_id, "success": False, "error": {"code": code, "message": message}})

    def _write(self, payload: dict[str, Any]) -> None:
        self._output_stream.write(json.dumps(payload) + "\n")
        self._output_stream.flush()
