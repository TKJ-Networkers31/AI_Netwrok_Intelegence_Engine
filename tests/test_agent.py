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


# --- Phase 1: fallback orchestration tests -----------------------------------


def test_agent_falls_back_when_primary_fails(
    fake_router_with_fallback, fake_provider, fake_fallback_provider
):
    fake_provider.should_fail = True
    fake_provider.error_code = ErrorCode.PROVIDER_UNAVAILABLE
    agent = Agent(router=fake_router_with_fallback)

    result = agent.run("Explain VLAN")

    assert result.success is True
    assert result.response == fake_fallback_provider.response
    assert result.metadata["used_fallback"] is True
    assert result.metadata["primary_error_code"] == ErrorCode.PROVIDER_UNAVAILABLE.value
    assert "request_id" in result.metadata
    # The fallback provider must have received the same Context.
    assert len(fake_fallback_provider.received_contexts) == 1


def test_agent_does_not_call_fallback_when_primary_succeeds(
    fake_router_with_fallback, fake_fallback_provider
):
    agent = Agent(router=fake_router_with_fallback)

    result = agent.run("Explain VLAN")

    assert result.success is True
    assert "used_fallback" not in result.metadata
    assert len(fake_fallback_provider.received_contexts) == 0


def test_agent_reports_structured_error_when_both_providers_fail(
    fake_router_with_fallback, fake_provider, fake_fallback_provider
):
    fake_provider.should_fail = True
    fake_provider.error_code = ErrorCode.CONNECTION_TIMEOUT
    fake_fallback_provider.should_fail = True
    fake_fallback_provider.error_code = ErrorCode.AUTHENTICATION_FAILED
    agent = Agent(router=fake_router_with_fallback)

    result = agent.run("Explain VLAN")

    assert result.success is False
    assert result.error.code == ErrorCode.ALL_PROVIDERS_FAILED
    assert result.error.details["primary_error"]["code"] == ErrorCode.CONNECTION_TIMEOUT.value
    assert result.error.details["fallback_error"]["code"] == ErrorCode.AUTHENTICATION_FAILED.value
    assert "request_id" in result.metadata


def test_agent_without_fallback_router_behaves_like_phase0(fake_router, fake_provider):
    """A router with no `get_fallback_provider` (e.g. any older test double)
    must behave exactly like Phase 0: no fallback attempted, ever.
    """
    fake_provider.should_fail = True
    fake_provider.error_code = ErrorCode.MODEL_UNAVAILABLE
    agent = Agent(router=fake_router)

    result = agent.run("Explain VLAN")

    assert result.success is False
    assert result.error.code == ErrorCode.MODEL_UNAVAILABLE
