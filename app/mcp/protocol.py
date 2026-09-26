"""The (minimal) wire protocol spoken between `app.mcp.client.MCPClient`
and `app.mcp.server.MCPServer`.

Deliberately tiny: three methods (`discover`, `invoke`, `ping`), a flat
newline-delimited-JSON envelope, and no capability negotiation, versioning,
or streaming. Anything transport-specific (stdio framing, subprocess
lifecycle) lives in `app.mcp.transport`, not here — this module only knows
about message *shapes*.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolSchema:
    """Metadata for a single tool, as returned by an MCP server's
    `discover` response and as consumed by `app.capabilities`."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolSchema":
        if "name" not in data:
            raise ValueError(f"Tool schema is missing 'name': {data!r}")
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("input_schema", {}) or {},
            output_schema=data.get("output_schema", {}) or {},
        )


@dataclass
class MCPRequest:
    id: str
    method: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "method": self.method, "params": self.params}

    @staticmethod
    def new(method: str, params: Optional[dict[str, Any]] = None) -> "MCPRequest":
        return MCPRequest(id=str(uuid.uuid4()), method=method, params=params or {})


@dataclass
class MCPResponse:
    id: Optional[str]
    success: bool
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Any) -> "MCPResponse":
        if not isinstance(data, dict) or "success" not in data:
            raise ValueError(f"Malformed MCP response: {data!r}")
        return cls(
            id=data.get("id"),
            success=bool(data["success"]),
            result=data.get("result"),
            error=data.get("error"),
        )
