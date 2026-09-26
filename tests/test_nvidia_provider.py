from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from app.core.types import Context, ErrorCode
from app.models.providers.nvidia import NvidiaProvider


def make_context() -> Context:
    context = Context(system_prompt="You are ANIE.")
    context.add_user_message("Explain VLAN")
    return context


def make_provider(api_key_env: str = "NVIDIA_API_KEY") -> NvidiaProvider:
    return NvidiaProvider(
        model="meta/llama-3.1-8b-instruct",
        base_url="https://integrate.api.nvidia.com/v1",
        timeout_seconds=5.0,
        api_key_env=api_key_env,
    )


@patch("app.models.providers.nvidia.requests.post")
def test_generate_success(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "A VLAN is..."}}]
    }
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is True
    assert result.response == "A VLAN is..."
    assert result.metadata["provider"] == "nvidia"
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["model"] == "meta/llama-3.1-8b-instruct"
    assert kwargs["json"]["stream"] is False
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"


def test_generate_missing_api_key_fails_without_network_call(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.AUTHENTICATION_FAILED
    # The env var *name* may appear in the message, the key value never can
    # (there is no key value here at all — this is the "not set" case).
    assert "NVIDIA_API_KEY" in result.error.message


@patch("app.models.providers.nvidia.requests.post")
def test_generate_handles_authentication_failure(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "bad-key")
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "unauthorized"
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.AUTHENTICATION_FAILED
    assert "bad-key" not in result.error.message


@patch("app.models.providers.nvidia.requests.post")
def test_generate_handles_timeout(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_post.side_effect = requests.exceptions.Timeout()

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.CONNECTION_TIMEOUT


@patch("app.models.providers.nvidia.requests.post")
def test_generate_handles_connection_error(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_post.side_effect = requests.exceptions.ConnectionError("refused")

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.PROVIDER_UNAVAILABLE


@patch("app.models.providers.nvidia.requests.post")
def test_generate_handles_model_not_found(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "model not found"
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.MODEL_UNAVAILABLE


@patch("app.models.providers.nvidia.requests.post")
def test_generate_handles_server_error(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "internal error"
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.PROVIDER_UNAVAILABLE


@patch("app.models.providers.nvidia.requests.post")
def test_generate_handles_malformed_response(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []}
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.MODEL_REQUEST_FAILED


@patch("app.models.providers.nvidia.requests.get")
def test_health_check_true(mock_get, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    provider = make_provider()

    assert provider.health_check() is True


def test_health_check_false_without_api_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    provider = make_provider()

    assert provider.health_check() is False


@patch("app.models.providers.nvidia.requests.get")
def test_health_check_false_on_connection_error(mock_get, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_get.side_effect = requests.exceptions.ConnectionError()

    provider = make_provider()

    assert provider.health_check() is False


# --- Phase 2: tool-calling passthrough ---------------------------------


@patch("app.models.providers.nvidia.requests.post")
def test_generate_passes_tools_and_parses_tool_calls(mock_post, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": "ping",
                                "arguments": '{"host": "10.0.0.1"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    context = make_context()
    context.tools = [{"type": "function", "function": {"name": "ping", "parameters": {}}}]

    provider = make_provider()
    result = provider.generate(context)

    assert result.success is True
    assert result.response is None
    assert result.tool_calls is not None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "ping"
    assert result.tool_calls[0].arguments == {"host": "10.0.0.1"}
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["tools"] == context.tools
