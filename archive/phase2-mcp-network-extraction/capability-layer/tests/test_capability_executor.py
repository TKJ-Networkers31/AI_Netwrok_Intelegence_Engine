from __future__ import annotations

from app.capabilities.executor import CapabilityExecutor, ToolResult
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import CapabilityDefinition, RiskLevel
from app.mcp.errors import MCPConnectionError, MCPMalformedResponseError, MCPTimeoutError
from app.mcp.protocol import MCPResponse

PING_SCHEMA = {
    "type": "object",
    "properties": {"host": {"type": "string"}},
    "required": ["host"],
    "additionalProperties": False,
}


class FakeMCPClient:
    def __init__(self, response=None, raise_error=None):
        self.response = response
        self.raise_error = raise_error
        self.invocations: list[tuple[str, dict]] = []

    def invoke_tool(self, name, arguments):
        self.invocations.append((name, arguments))
        if self.raise_error is not None:
            raise self.raise_error
        return self.response


def _registry_with_ping(risk_level=RiskLevel.READ_ONLY, server="generic") -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDefinition(
            name="ping",
            description="ping a host",
            server=server,
            input_schema=PING_SCHEMA,
            output_schema={"type": "object"},
            risk_level=risk_level,
        )
    )
    return registry


def test_execute_unknown_capability():
    registry = CapabilityRegistry()
    executor = CapabilityExecutor(registry, {})

    result = executor.execute("not_real", {})

    assert result.success is False
    assert result.error["code"] == "unknown_capability"


def test_execute_invalid_arguments_never_calls_mcp_client():
    registry = _registry_with_ping()
    client = FakeMCPClient()
    executor = CapabilityExecutor(registry, {"generic": client})

    result = executor.execute("ping", {})  # missing required 'host'

    assert result.success is False
    assert result.error["code"] == "invalid_arguments"
    assert client.invocations == []


def test_execute_rejects_non_read_only_capability():
    registry = _registry_with_ping(risk_level=RiskLevel.MEDIUM)
    client = FakeMCPClient()
    executor = CapabilityExecutor(registry, {"generic": client})

    result = executor.execute("ping", {"host": "10.0.0.1"})

    assert result.success is False
    assert result.error["code"] == "permission_denied"
    assert client.invocations == []


def test_execute_server_unavailable_when_no_client_connected():
    registry = _registry_with_ping()
    executor = CapabilityExecutor(registry, {})  # no clients at all

    result = executor.execute("ping", {"host": "10.0.0.1"})

    assert result.success is False
    assert result.error["code"] == "server_unavailable"


def test_execute_success():
    registry = _registry_with_ping()
    client = FakeMCPClient(response=MCPResponse(id="1", success=True, result={"reachable": True}))
    executor = CapabilityExecutor(registry, {"generic": client})

    result = executor.execute("ping", {"host": "10.0.0.1"})

    assert result.success is True
    assert result.data == {"reachable": True}
    assert result.metadata["server"] == "generic"
    assert client.invocations == [("ping", {"host": "10.0.0.1"})]


def test_execute_mcp_server_reports_failure():
    registry = _registry_with_ping()
    client = FakeMCPClient(
        response=MCPResponse(id="1", success=False, error={"code": "connection_failed", "message": "no route"})
    )
    executor = CapabilityExecutor(registry, {"generic": client})

    result = executor.execute("ping", {"host": "10.0.0.1"})

    assert result.success is False
    assert result.error["code"] == "connection_failed"


def test_execute_wraps_mcp_timeout():
    registry = _registry_with_ping()
    client = FakeMCPClient(raise_error=MCPTimeoutError("slow"))
    executor = CapabilityExecutor(registry, {"generic": client})

    result = executor.execute("ping", {"host": "10.0.0.1"})

    assert result.success is False
    assert result.error["code"] == "mcp_timeout"


def test_execute_wraps_mcp_connection_error():
    registry = _registry_with_ping()
    client = FakeMCPClient(raise_error=MCPConnectionError("down"))
    executor = CapabilityExecutor(registry, {"generic": client})

    result = executor.execute("ping", {"host": "10.0.0.1"})

    assert result.success is False
    assert result.error["code"] == "mcp_connection_failed"


def test_execute_wraps_mcp_malformed_response():
    registry = _registry_with_ping()
    client = FakeMCPClient(raise_error=MCPMalformedResponseError("bad json"))
    executor = CapabilityExecutor(registry, {"generic": client})

    result = executor.execute("ping", {"host": "10.0.0.1"})

    assert result.success is False
    assert result.error["code"] == "mcp_malformed_response"


def test_get_tool_definitions_only_includes_read_only():
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDefinition(
            name="ping",
            description="ping a host",
            server="generic",
            input_schema=PING_SCHEMA,
            risk_level=RiskLevel.READ_ONLY,
        )
    )
    registry.register(
        CapabilityDefinition(
            name="reboot_device",
            description="reboot a device",
            server="mikrotik",
            input_schema={},
            risk_level=RiskLevel.HIGH,
        )
    )
    executor = CapabilityExecutor(registry, {})

    definitions = executor.get_tool_definitions()

    names = [d["function"]["name"] for d in definitions]
    assert names == ["ping"]
    assert definitions[0]["type"] == "function"
    assert definitions[0]["function"]["parameters"] == PING_SCHEMA


def test_tool_result_to_dict_success_and_error():
    success = ToolResult(True, "ping", data={"ok": True}, metadata={"server": "generic"})
    failure = ToolResult(False, "ping", error={"code": "x", "message": "y"})

    assert success.to_dict() == {
        "success": True,
        "tool": "ping",
        "data": {"ok": True},
        "metadata": {"server": "generic"},
    }
    assert failure.to_dict() == {"success": False, "tool": "ping", "error": {"code": "x", "message": "y"}}
