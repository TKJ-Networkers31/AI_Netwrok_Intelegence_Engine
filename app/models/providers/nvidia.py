"""NVIDIA model provider.

Talks to an NVIDIA NIM / integrate.api.nvidia.com style endpoint using the
OpenAI-compatible `/chat/completions` API. Used as the Phase 1 fallback
provider when the primary (Ollama) provider fails.

The API key is NEVER read from configuration or hardcoded — only the name
of the environment variable holding it is configurable (`api_key_env`,
default "NVIDIA_API_KEY"). The key value itself is never logged or placed
in an ExecutionError's message/details.
"""

from __future__ import annotations

import logging
import os

import requests

from app.core.types import Context, ErrorCode, ExecutionResult
from app.models.base import ModelProvider

logger = logging.getLogger("anie.provider.nvidia")

DEFAULT_API_KEY_ENV = "NVIDIA_API_KEY"


class NvidiaProvider(ModelProvider):
    """ModelProvider implementation backed by an NVIDIA-hosted endpoint."""

    def __init__(
        self,
        model: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        api_key_env: str = DEFAULT_API_KEY_ENV,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key_env = api_key_env or DEFAULT_API_KEY_ENV

    def _read_api_key(self) -> str | None:
        # Read fresh from the environment on every call rather than caching
        # at construction time, so a key set/rotated after startup is picked
        # up without restarting the process.
        return os.environ.get(self.api_key_env)

    def generate(self, context: Context) -> ExecutionResult:
        api_key = self._read_api_key()
        if not api_key:
            logger.error(
                "model.error",
                extra={"component": "nvidia_provider", "event": "model.error", "reason": "missing_api_key"},
            )
            return ExecutionResult.fail(
                ErrorCode.AUTHENTICATION_FAILED,
                f"NVIDIA API key not set. Export the {self.api_key_env} "
                f"environment variable before running ANIE.",
            )

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": context.as_prompt_messages(),
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        logger.info(
            "model.request",
            extra={"component": "nvidia_provider", "event": "model.request", "model": self.model, "url": url},
        )

        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout_seconds
            )
        except requests.exceptions.Timeout:
            logger.error(
                "model.error",
                extra={"component": "nvidia_provider", "event": "model.error", "reason": "timeout"},
            )
            return ExecutionResult.fail(
                ErrorCode.CONNECTION_TIMEOUT,
                f"Timed out waiting for NVIDIA endpoint at {self.base_url} "
                f"after {self.timeout_seconds}s",
            )
        except requests.exceptions.ConnectionError as exc:
            logger.error(
                "model.error",
                extra={"component": "nvidia_provider", "event": "model.error", "reason": "connection_error"},
            )
            return ExecutionResult.fail(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"Could not connect to NVIDIA endpoint at {self.base_url}: {exc}",
            )
        except requests.exceptions.RequestException as exc:
            logger.error(
                "model.error",
                extra={"component": "nvidia_provider", "event": "model.error", "reason": "request_exception"},
            )
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                f"Request to NVIDIA endpoint failed: {exc}",
            )

        if response.status_code in (401, 403):
            logger.error(
                "model.error",
                extra={"component": "nvidia_provider", "event": "model.error", "reason": "authentication_failed"},
            )
            return ExecutionResult.fail(
                ErrorCode.AUTHENTICATION_FAILED,
                f"NVIDIA rejected the request as unauthorized (status "
                f"{response.status_code}). Check the {self.api_key_env} value.",
            )

        if response.status_code == 404:
            logger.error(
                "model.error",
                extra={"component": "nvidia_provider", "event": "model.error", "reason": "model_not_found"},
            )
            return ExecutionResult.fail(
                ErrorCode.MODEL_UNAVAILABLE,
                f"Model '{self.model}' was not found on the NVIDIA endpoint "
                f"at {self.base_url}.",
            )

        if response.status_code >= 500:
            return ExecutionResult.fail(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"NVIDIA server error (status {response.status_code}): {response.text}",
            )

        if response.status_code >= 400:
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                f"NVIDIA rejected the request (status {response.status_code}): "
                f"{response.text}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                f"NVIDIA returned a non-JSON response: {exc}",
            )

        choices = data.get("choices") or []
        content = None
        if choices:
            content = (choices[0].get("message") or {}).get("content")

        if not content:
            return ExecutionResult.fail(
                ErrorCode.MODEL_REQUEST_FAILED,
                "NVIDIA response did not contain a message content field.",
                details={"raw_response": data},
            )

        logger.info(
            "model.response",
            extra={"component": "nvidia_provider", "event": "model.response", "model": self.model},
        )
        return ExecutionResult.ok(content, model=self.model, provider="nvidia")

    def health_check(self) -> bool:
        api_key = self._read_api_key()
        if not api_key:
            return False
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=self.timeout_seconds,
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def capabilities(self) -> dict[str, bool]:
        return {
            "text": True,
            "streaming": False,
            "tool_calling": False,
            "vision": False,
        }
