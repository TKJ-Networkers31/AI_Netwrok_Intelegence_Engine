"""Wires `config.mcp.servers` into a ready-to-use `CapabilityExecutor`.

Connecting to an MCP server is treated as optional/best-effort, unlike
`ModelRouter` (which fails fast on bad *model* config): the MCP/tool layer
sits on top of the core Agent, not underneath it, so a misconfigured or
unreachable MCP server shouldn't prevent ANIE from starting at all — it
should just mean the capabilities routed to that server report
`server_unavailable` when a model tries to use them.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.capabilities.executor import CapabilityExecutor
from app.capabilities.registry import CapabilityRegistry
from app.core.config import Config
from app.mcp.client import MCPClient
from app.mcp.errors import MCPError
from app.mcp.transport import StdioTransport

logger = logging.getLogger("anie.mcp.bootstrap")


def build_capability_executor(config: Config, registry: CapabilityRegistry) -> Optional[CapabilityExecutor]:
    """Connect every configured MCP server and return a `CapabilityExecutor`
    wired to whichever ones connected successfully.

    Returns `None` if no servers are configured, or if every configured
    server failed to connect (in which case there is nothing a
    `CapabilityExecutor` could usefully do — the Agent treats a `None`
    executor as "no tools available", matching Phase 0/1 behavior exactly).
    """
    if not config.mcp.servers:
        return None

    clients: dict[str, MCPClient] = {}
    for server_config in config.mcp.servers:
        transport = StdioTransport(command=server_config.command, args=list(server_config.args))
        client = MCPClient(transport, timeout_seconds=server_config.timeout_seconds, name=server_config.name)
        try:
            client.connect()
        except MCPError:
            logger.warning(
                "mcp.connect_failed",
                extra={
                    "component": "mcp_bootstrap",
                    "event": "mcp.connect_failed",
                    "server": server_config.name,
                },
            )
            continue
        clients[server_config.name] = client

    if not clients:
        return None
    return CapabilityExecutor(registry, clients)
