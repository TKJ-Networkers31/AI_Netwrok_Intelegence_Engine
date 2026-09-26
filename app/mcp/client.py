"""Minimal, transport-independent MCP client.

Speaks the tiny request/response protocol in `app.mcp.protocol` over
whatever `Transport` it's given (`app.mcp.transport`). It doesn't know or
care about MikroTik, RouterOS, or any other vendor — that lives entirely in
the adapter/server layer (`app.adapters`, `app.mcp.servers`).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.mcp.errors import (
    MCPConnectionError,
    MCPDisconnectedError,
    MCPMalformedResponseError,
    MCPNotConnectedError,
    MCPTimeoutError,
)
from app.mcp.protocol import MCPRequest, MCPResponse, ToolSchema
from app.mcp.transport import Transport

logger = logging.getLogger("anie.mcp.client")


class MCPClient:
    """Connects to a single MCP server over a `Transport` and exposes
    `discover_tools()` / `invoke_tool()`.
    """

    def __init__(self, transport: Transport, timeout_seconds: float = 10.0, name: str = "mcp"):
        self._transport = transport
        self.timeout_seconds = timeout_seconds
        self.name = name
        self._connected = False
        self._tools: Optional[dict[str, ToolSchema]] = None

    def connect(self) -> None:
        try:
            self._transport.connect()
        except Exception as exc:
            raise MCPConnectionError(f"Could not start MCP server '{self.name}': {exc}") from exc
        self._connected = True
        logger.info(
            "mcp.connect", extra={"component": "mcp_client", "event": "mcp.connect", "server": self.name}
        )

    def disconnect(self) -> None:
        self._transport.disconnect()
        self._connected = False
        logger.info(
            "mcp.disconnect",
            extra={"component": "mcp_client", "event": "mcp.disconnect", "server": self.name},
        )

    @property
    def is_connected(self) -> bool:
        return self._connected

    def discover_tools(self, force: bool = False) -> list[ToolSchema]:
        """Return the tools this server exposes, caching the result until
        `force=True` is passed (servers in Phase 2 have a static tool set)."""
        if self._tools is not None and not force:
            return list(self._tools.values())

        response = self._send("discover", {})
        if not response.success:
            raise MCPMalformedResponseError(
                f"MCP server '{self.name}' rejected discovery: {response.error}"
            )

        raw_tools = (response.result or {}).get("tools", [])
        try:
            tools = [ToolSchema.from_dict(t) for t in raw_tools]
        except (ValueError, TypeError, KeyError) as exc:
            raise MCPMalformedResponseError(
                f"MCP server '{self.name}' returned malformed tool schemas: {exc}"
            ) from exc

        self._tools = {tool.name: tool for tool in tools}
        return tools

    def invoke_tool(self, name: str, arguments: dict[str, Any]) -> MCPResponse:
        """Invoke a tool by name and return the raw `MCPResponse`.

        Normalization into ANIE's `ToolResult` contract happens one layer
        up, in `app.capabilities.executor.CapabilityExecutor` — this client
        only speaks the MCP protocol.
        """
        return self._send("invoke", {"tool": name, "arguments": arguments})

    def ping(self) -> bool:
        """Lightweight liveness check against the server (raises the same
        MCPError subclasses as `discover_tools`/`invoke_tool` on failure)."""
        response = self._send("ping", {})
        return response.success

    def _send(self, method: str, params: dict[str, Any]) -> MCPResponse:
        if not self._connected:
            raise MCPNotConnectedError(f"MCP client for '{self.name}' is not connected.")

        request = MCPRequest.new(method, params)
        try:
            self._transport.send(request.to_dict())
        except Exception as exc:
            self._connected = False
            raise MCPConnectionError(f"Failed to send request to '{self.name}': {exc}") from exc

        try:
            raw = self._transport.receive(self.timeout_seconds)
        except TimeoutError as exc:
            raise MCPTimeoutError(
                f"MCP server '{self.name}' did not respond within {self.timeout_seconds}s"
            ) from exc
        except Exception as exc:
            self._connected = False
            raise MCPConnectionError(f"Failed to read response from '{self.name}': {exc}") from exc

        if raw is None:
            self._connected = False
            raise MCPDisconnectedError(f"MCP server '{self.name}' closed the connection.")

        try:
            return MCPResponse.from_dict(raw)
        except (ValueError, KeyError, TypeError) as exc:
            raise MCPMalformedResponseError(
                f"MCP server '{self.name}' returned a malformed response: {exc}"
            ) from exc

    def __enter__(self) -> "MCPClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()
