from __future__ import annotations

from app.capabilities.executor import CapabilityExecutor
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import CapabilityDefinition
from app.core.agent import Agent
from app.core.types import Context, ErrorCode, ExecutionResult, ToolCall
from app.mcp.protocol import MCPResponse


class ToolCallingFakeProvider:
    """Requests a tool call on the first `generate()`, then returns a plain
    text response on the second (and any subsequent) call."""

    def __init__(self, tool_calls, final_response="final answer"):
        self.tool_calls = tool_calls
        self.final_response = final_response
        self.call_count = 0
        self.received_contexts: list[Context] = []

    def generate(self, context: Context) -> ExecutionResult:
        self.received_contexts.append(context)
        self.call_count += 1
        if self.call_count == 1:
            return ExecutionResult.tool_call_requested(self.tool_calls, provider="fake")
        return ExecutionResult.ok(self.final_response, provider="fake")

    def health_check(self) -> bool:
        return True


class AlwaysToolCallingFakeProvider:
    """Always requests the same tool call — used to test the iteration cap."""

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.call_count = 0

    def generate(self, context: Context) -> ExecutionResult:
        self.call_count += 1
        return ExecutionResult.tool_call_requested(self.tool_calls, provider="fake")

    def health_check(self) -> bool:
        return True


class FakeMCPClient:
    def __init__(self, response: MCPResponse):
        self.response = response
        self.invocations: list[tuple[str, dict]] = []

    def invoke_tool(self, name, arguments):
        self.invocations.append((name, arguments))
        return self.response


class SimpleRouter:
    """A router with no fallback — just enough for these tests."""

    def __init__(self, provider):
        self._provider = provider

    def get_provider(self):
        return self._provider

    def get_fallback_provider(self):
        return None


def _build_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDefinition(
            name="ping",
            description="ping a host",
            server="generic",
            input_schema={
                "type": "object",
                "properties": {"host": {"type": "string"}},
                "required": ["host"],
            },
        )
    )
    return registry


def test_agent_executes_requested_tool_and_returns_final_response():
    tool_call = ToolCall(id="call_1", name="ping", arguments={"host": "10.0.0.1"})
    provider = ToolCallingFakeProvider([tool_call])
    router = SimpleRouter(provider)
    registry = _build_registry()
    fake_client = FakeMCPClient(MCPResponse(id="1", success=True, result={"reachable": True}))
    executor = CapabilityExecutor(registry, {"generic": fake_client})
    agent = Agent(router=router, tool_executor=executor)

    result = agent.run("Ping 10.0.0.1")

    assert result.success is True
    assert result.response == "final answer"
    assert provider.call_count == 2
    assert fake_client.invocations == [("ping", {"host": "10.0.0.1"})]
    # The model's tools list was populated from the registry.
    assert provider.received_contexts[0].tools is not None
    assert any(t["function"]["name"] == "ping" for t in provider.received_contexts[0].tools)


def test_agent_reports_tool_error_to_model_and_still_gets_final_response():
    tool_call = ToolCall(id="call_1", name="ping", arguments={"host": "10.0.0.1"})
    provider = ToolCallingFakeProvider([tool_call])
    router = SimpleRouter(provider)
    registry = _build_registry()
    fake_client = FakeMCPClient(
        MCPResponse(id="1", success=False, error={"code": "connection_failed", "message": "no route"})
    )
    executor = CapabilityExecutor(registry, {"generic": fake_client})
    agent = Agent(router=router, tool_executor=executor)

    result = agent.run("Ping 10.0.0.1")

    assert result.success is True
    assert result.response == "final answer"
    # The tool failure must have been surfaced to the model as a tool message.
    last_context = provider.received_contexts[-1]
    tool_messages = [m for m in last_context.messages if m.role.value == "tool"]
    assert len(tool_messages) == 1
    assert "connection_failed" in tool_messages[0].content


def test_agent_rejects_unregistered_tool_without_calling_any_mcp_client():
    tool_call = ToolCall(id="call_1", name="not_a_real_tool", arguments={})
    provider = ToolCallingFakeProvider([tool_call])
    router = SimpleRouter(provider)
    registry = _build_registry()
    fake_client = FakeMCPClient(MCPResponse(id="1", success=True, result={}))
    executor = CapabilityExecutor(registry, {"generic": fake_client})
    agent = Agent(router=router, tool_executor=executor)

    result = agent.run("do something sketchy")

    assert result.success is True
    assert fake_client.invocations == []


def test_agent_without_tool_executor_ignores_tool_calls_field():
    tool_call = ToolCall(id="call_1", name="ping", arguments={"host": "10.0.0.1"})
    provider = ToolCallingFakeProvider([tool_call])
    router = SimpleRouter(provider)
    agent = Agent(router=router)  # no tool_executor

    result = agent.run("ping something")

    assert provider.call_count == 1
    assert result.tool_calls == [tool_call]
    assert result.response is None


def test_agent_stops_after_max_tool_iterations():
    tool_call = ToolCall(id="call_1", name="ping", arguments={"host": "10.0.0.1"})
    provider = AlwaysToolCallingFakeProvider([tool_call])
    router = SimpleRouter(provider)
    registry = _build_registry()
    fake_client = FakeMCPClient(MCPResponse(id="1", success=True, result={"reachable": True}))
    executor = CapabilityExecutor(registry, {"generic": fake_client})
    agent = Agent(router=router, tool_executor=executor, max_tool_iterations=2)

    result = agent.run("ping forever")

    assert result.success is False
    assert result.error.code == ErrorCode.TOOL_EXECUTION_FAILED
    # initial generate() + 2 bounded iterations = 3 total provider calls
    assert provider.call_count == 3
    assert len(fake_client.invocations) == 2
