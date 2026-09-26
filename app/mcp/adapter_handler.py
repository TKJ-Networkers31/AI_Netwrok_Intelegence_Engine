"""Bridges an `app.adapters.base.Adapter` (+ its `CapabilityDefinition`s)
into the shape `app.mcp.server.MCPServer` expects (`list_tools` / `invoke`).

Keeps `Adapter` implementations vendor-focused (RouterOS, system `ping`,
etc.) and free of any MCP-protocol concerns.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.adapters.base import Adapter
from app.capabilities.types import CapabilityDefinition
from app.mcp.protocol import ToolSchema


class AdapterToolHandler:
    def __init__(self, adapter: Adapter, capabilities: Iterable[CapabilityDefinition]):
        supported = set(adapter.list_capabilities())
        self._adapter = adapter
        self._capabilities = {cap.name: cap for cap in capabilities if cap.name in supported}

    def list_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name=cap.name,
                description=cap.description,
                input_schema=cap.input_schema,
                output_schema=cap.output_schema,
            )
            for cap in self._capabilities.values()
        ]

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._capabilities:
            return {
                "success": False,
                "error": {"code": "unknown_tool", "message": f"'{name}' is not exposed by this server."},
            }
        return self._adapter.invoke(name, arguments)
