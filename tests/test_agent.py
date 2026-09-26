from __future__ import annotations

from app.core.agent import Agent
from app.core.types import ErrorCode


def test_agent_accepts_input_and_returns_structured_result(fake_router, fake_provider):
    agent = Agent(router=fake_router)

    result = agent.run("Explain VLAN")

    assert result.success is True
    assert result.response == fake_provider.response
    assert "request_id" in result.metadata
    # The provider should have received a Context built from the input
    assert len(fake_provider.received_contexts) == 1
    context = fake_provider.received_contexts[0]
    assert context.messages[-1].content == "Explain VLAN"


def test_agent_returns_structured_result_on_provider_error(fake_router, fake_provider):
    fake_provider.should_fail = True
    fake_provider.error_code = ErrorCode.PROVIDER_UNAVAILABLE
    agent = Agent(router=fake_router)

    result = agent.run("Explain trunking")

    assert result.success is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_UNAVAILABLE
    assert "request_id" in result.metadata


def test_agent_builds_context_with_system_prompt(fake_router):
    agent = Agent(router=fake_router, system_prompt="custom system prompt")

    context = agent._build_context("hello")

    assert context.system_prompt == "custom system prompt"
    assert context.messages[0].content == "hello"
