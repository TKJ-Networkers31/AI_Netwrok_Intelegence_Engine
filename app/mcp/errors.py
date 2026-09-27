"""Structured error types raised by the MCP client.

Mirrors the way `app.models.base.ModelProvider` implementations turn
expected failure modes into `ExecutionResult.fail(...)` rather than letting
raw exceptions cross abstraction boundaries — the MCP client instead raises
a small, closed set of typed exceptions that a host-side tool-execution
layer (see `app.core.agent.ToolExecutor`) can catch and turn into a
structured tool result. ANIE's own `CapabilityExecutor` implementation of
that layer was extracted to `archive/phase2-mcp-network-extraction/` — see
README.md.
"""

from __future__ import annotations


class MCPError(Exception):
    """Base class for all MCP client errors."""


class MCPConnectionError(MCPError):
    """Could not connect to, or lost the connection to, an MCP server."""


class MCPTimeoutError(MCPError):
    """An MCP server did not respond within the configured timeout."""


class MCPMalformedResponseError(MCPError):
    """An MCP server returned a response that could not be parsed."""


class MCPDisconnectedError(MCPError):
    """An MCP server closed the connection unexpectedly."""


class MCPNotConnectedError(MCPError):
    """A request was made before `connect()` succeeded."""
