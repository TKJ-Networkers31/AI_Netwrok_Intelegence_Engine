"""Ollama model provider.

Talks to a local (or remote) Ollama server via its HTTP API
(https://github.com/ollama/ollama/blob/main/docs/api.md).
"""

from __future__ import annotations

import json
import logging

import requests

from app.core.types import Context, ErrorCode, ExecutionResult, ToolCall
from app.models.base import ModelProvider

logger = logging.getLogger("anie.provider.ollama")


def _parse_tool_calls(raw_tool_calls: list[dict]) -> list[ToolCall]:
    """Normalize a provider-native tool_calls list into ToolCall objects.

    Ollama's chat API (when a model supports tool calling) returns
    `message.tool_calls` as a list of `{"function": {"name", "arguments"}}`
    entries, with `arguments` already a dict (unlike NVIDIA/OpenAI-style
    APIs, which send it as a JSON string) -- handle both shapes to be safe.
    """
    tool_calls: list[ToolCall] = []
    for index, raw in enumerate(raw_tool_calls or []):
        function = raw.get("function") or {}
        name = function.get("name", "")
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (ValueError, TypeError):
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_calls.append(ToolCall(id=raw.get("id") or f"call_{index}", name=name, arguments=arguments))
    return tool_calls


class OllamaProvider(ModelProvider):
    """ModelProvider implementation backed by an Ollama server."""

    def __init__(self, model: str, base_url: str, timeout_seconds: float = 60.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def generate(self, context: Context) -> ExecutionResult:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": context.as_prompt_messages(),
            "stream": False,
        }
        if context.tools:
            payload["tools"] = context.tools

        logger.info(
            "model.request",
            extra={"component": "ollama_provider", "event": "model.request", "model": self.model, "url": url},
        )

        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        except requests.exceptions.Timeout:
            logger.error(
                "model.error",
                extra={"component": "ollama_provider", "event": "model.error", "reason": "timeout"},
            )
            return ExecutionResult.fail(
                ErrorCode.CONNECTION_TIMEOUT,
                f"Timed out waiting for Ollama at {self.base_url} "
                f"after {self.timeout_seconds}s",
            )
        except requests.exceptions.ConnectionError as exc:
            logger.error(
                "model.error",
                extra={"component": "ollama_provider", "event": "model.error", "reason": "connection_error"},
            )
            return ExecutionResult.fail(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"Could not connect to Ollama at {self.base_url}: {exc}",
            )
        except requests.exceptions.RequestException as exc:
            logger.error(
                "model.error",
                extra={"component": "ollama_provider", "event": "model.error", "reason": "request_exception"},
            )
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                f"Request to Ollama failed: {exc}",
            )

        if response.status_code == 404:
            logger.error(
                "model.error",
                extra={"component": "ollama_provider", "event": "model.error", "reason": "model_not_found"},
            )
            return ExecutionResult.fail(
                ErrorCode.MODEL_UNAVAILABLE,
                f"Model '{self.model}' was not found on the Ollama server "
                f"at {self.base_url}. Has it been pulled (`ollama pull {self.model}`)?",
            )

        if response.status_code >= 500:
            return ExecutionResult.fail(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"Ollama server error (status {response.status_code}): {response.text}",
            )

        if response.status_code >= 400:
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                f"Ollama rejected the request (status {response.status_code}): "
                f"{response.text}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                f"Ollama returned a non-JSON response: {exc}",
            )

        message = data.get("message") or {}

        tool_calls_raw = message.get("tool_calls")
        if tool_calls_raw:
            tool_calls = _parse_tool_calls(tool_calls_raw)
            logger.info(
                "model.tool_call",
                extra={"component": "ollama_provider", "event": "model.tool_call", "model": self.model},
            )
            return ExecutionResult.tool_call_requested(tool_calls, model=self.model, provider="ollama")

        content = message.get("content")
        if not content:
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                "Ollama response did not contain a message content field.",
                details={"raw_response": data},
            )

        logger.info(
            "model.response",
            extra={"component": "ollama_provider", "event": "model.response", "model": self.model},
        )
        return ExecutionResult.ok(content, model=self.model, provider="ollama")

    def health_check(self) -> bool:
        try:
            response = requests.get(
                f"{self.base_url}/api/tags", timeout=self.timeout_seconds
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def capabilities(self) -> dict[str, bool]:
        return {
            "text": True,
            "streaming": False,
            "tool_calling": True,
            "vision": False,
        }
