"""The Phase 2 execution boundary.

Flow (per the spec):

    model tool request
    -> registry lookup           (CapabilityRegistry.get)
    -> schema validation         (app.capabilities.validation.validate_arguments)
    -> permission/risk validation (RiskLevel check)
    -> MCP invocation            (MCPClient.invoke_tool)
    -> normalized result         (ToolResult)

Every step can reject the request with a structured error; nothing here
ever fabricates device data, executes arbitrary code, or falls through to a
"just try it anyway" path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import RiskLevel
from app.capabilities.validation import validate_arguments
from app.mcp.client import MCPClient
from app.mcp.errors import MCPConnectionError, MCPError, MCPMalformedResponseError, MCPTimeoutError

logger = logging.getLogger("anie.capabilities.executor")


@dataclass
class ToolResult:
    """The Phase 2 "result contract" from the spec, as a Python object."""

    success: bool
    tool: str
    data: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"success": self.success, "tool": self.tool}
        if self.success:
            payload["data"] = self.data or {}
        else:
            payload["error"] = self.error or {
                "code": "unknown_error",
                "message": "Tool invocation failed.",
            }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


class CapabilityExecutor:
    """Validates and routes a model-requested tool call to the right MCP
    server, normalizing whatever comes back into a `ToolResult`.

    `clients` maps a capability's `server` name (as declared in its
    `CapabilityDefinition`, matching `config.mcp.servers[].name`) to an
    already-connected `MCPClient`. A capability whose server has no
    connected client fails with `server_unavailable` rather than raising.
    """

    def __init__(self, registry: CapabilityRegistry, clients: dict[str, MCPClient]):
        self.registry = registry
        self.clients = clients

    def execute(self, capability_name: str, arguments: dict[str, Any]) -> ToolResult:
        capability = self.registry.get(capability_name)
        if capability is None:
            logger.warning(
                "tool.rejected",
                extra={"component": "executor", "event": "tool.rejected", "reason": "unknown_capability"},
            )
            return ToolResult(
                False,
                capability_name,
                error={
                    "code": "unknown_capability",
                    "message": f"'{capability_name}' is not a registered capability.",
                },
            )

        validation_errors = validate_arguments(capability.input_schema, arguments)
        if validation_errors:
            logger.warning(
                "tool.rejected",
                extra={"component": "executor", "event": "tool.rejected", "reason": "invalid_arguments"},
            )
            return ToolResult(
                False,
                capability_name,
                error={"code": "invalid_arguments", "message": "; ".join(validation_errors)},
            )

        if capability.risk_level != RiskLevel.READ_ONLY:
            # Nothing in Phase 2 registers a higher risk level, but this
            # check exists so a future capability can't accidentally become
            # invocable just by being added to the registry.
            logger.warning(
                "tool.rejected",
                extra={"component": "executor", "event": "tool.rejected", "reason": "permission_denied"},
            )
            return ToolResult(
                False,
                capability_name,
                error={
                    "code": "permission_denied",
                    "message": (
                        f"Capability '{capability_name}' requires risk level "
                        f"'{capability.risk_level.value}', which is not permitted by default."
                    ),
                },
            )

        client = self.clients.get(capability.server)
        if client is None:
            return ToolResult(
                False,
                capability_name,
                error={
                    "code": "server_unavailable",
                    "message": f"No MCP server is connected for '{capability.server}'.",
                },
            )

        try:
            response = client.invoke_tool(capability_name, arguments)
        except MCPTimeoutError as exc:
            return ToolResult(False, capability_name, error={"code": "mcp_timeout", "message": str(exc)})
        except MCPConnectionError as exc:
            return ToolResult(
                False, capability_name, error={"code": "mcp_connection_failed", "message": str(exc)}
            )
        except MCPMalformedResponseError as exc:
            return ToolResult(
                False, capability_name, error={"code": "mcp_malformed_response", "message": str(exc)}
            )
        except MCPError as exc:
            return ToolResult(False, capability_name, error={"code": "mcp_error", "message": str(exc)})

        if response.success:
            return ToolResult(
                True, capability_name, data=response.result or {}, metadata={"server": capability.server}
            )
        return ToolResult(
            False,
            capability_name,
            error=response.error or {"code": "unknown_error", "message": "Tool invocation failed."},
            metadata={"server": capability.server},
        )

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """OpenAI-style `tools` array for model integration
        (`app.core.types.Context.tools`). Only read-only, registered
        capabilities are ever exposed to the model — the same allowlist
        `execute()` enforces.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": cap.name,
                    "description": cap.description,
                    "parameters": cap.input_schema,
                },
            }
            for cap in self.registry.list_all()
            if cap.risk_level == RiskLevel.READ_ONLY
        ]
