from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from app.core.types import Context, ErrorCode
from app.models.providers.ollama import OllamaProvider


def make_context() -> Context:
    context = Context(system_prompt="You are ANIE.")
    context.add_user_message("Explain VLAN")
    return context


def make_provider() -> OllamaProvider:
    return OllamaProvider(
        model="qwen3:1.7b", base_url="http://localhost:11434", timeout_seconds=5.0
    )


@patch("app.models.providers.ollama.requests.post")
def test_generate_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"role": "assistant", "content": "A VLAN is..."}}
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is True
    assert result.response == "A VLAN is..."
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["model"] == "qwen3:1.7b"
    assert kwargs["json"]["stream"] is False


@patch("app.models.providers.ollama.requests.post")
def test_generate_handles_timeout(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout()

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.CONNECTION_TIMEOUT


@patch("app.models.providers.ollama.requests.post")
def test_generate_handles_connection_error(mock_post):
    mock_post.side_effect = requests.exceptions.ConnectionError("refused")

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.PROVIDER_UNAVAILABLE


@patch("app.models.providers.ollama.requests.post")
def test_generate_handles_model_not_found(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "model not found"
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.MODEL_UNAVAILABLE


@patch("app.models.providers.ollama.requests.post")
def test_generate_handles_server_error(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "internal error"
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.PROVIDER_UNAVAILABLE


@patch("app.models.providers.ollama.requests.post")
def test_generate_handles_empty_content(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"role": "assistant", "content": ""}}
    mock_post.return_value = mock_response

    provider = make_provider()
    result = provider.generate(make_context())

    assert result.success is False
    assert result.error.code == ErrorCode.MODEL_REQUEST_FAILED


@patch("app.models.providers.ollama.requests.get")
def test_health_check_true(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    provider = make_provider()

    assert provider.health_check() is True


@patch("app.models.providers.ollama.requests.get")
def test_health_check_false_on_bad_status(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_get.return_value = mock_response

    provider = make_provider()

    assert provider.health_check() is False


@patch("app.models.providers.ollama.requests.get")
def test_health_check_false_on_connection_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError()

    provider = make_provider()

    assert provider.health_check() is False


# --- Phase 2: tool-calling passthrough ---------------------------------


@patch("app.models.providers.ollama.requests.post")
def test_generate_passes_tools_and_parses_tool_calls(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "ping", "arguments": {"host": "10.0.0.1"}}}
            ],
        }
    }
    mock_post.return_value = mock_response

    context = make_context()
    context.tools = [{"type": "function", "function": {"name": "ping", "parameters": {}}}]

    provider = make_provider()
    result = provider.generate(context)

    assert result.success is True
    assert result.response is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "ping"
    assert result.tool_calls[0].arguments == {"host": "10.0.0.1"}
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["tools"] == context.tools
