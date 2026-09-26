from __future__ import annotations

from typing import Optional

import pytest

from app.core.config import AppConfig, Config, ModelConfig, RuntimeConfig
from app.core.types import Context, ErrorCode, ExecutionResult
from app.models.base import ModelProvider


class FakeProvider(ModelProvider):
    """A configurable fake provider for unit tests."""

    def __init__(
        self,
        response: str = "fake response",
        should_fail: bool = False,
        healthy: bool = True,
        error_code: ErrorCode = ErrorCode.MODEL_REQUEST_FAILED,
    ):
        self.response = response
        self.should_fail = should_fail
        self.healthy = healthy
        self.error_code = error_code
        self.received_contexts: list[Context] = []

    def generate(self, context: Context) -> ExecutionResult:
        self.received_contexts.append(context)
        if self.should_fail:
            return ExecutionResult.fail(self.error_code, "fake failure")
        return ExecutionResult.ok(self.response, provider="fake")

    def health_check(self) -> bool:
        return self.healthy


@pytest.fixture
def valid_config() -> Config:
    return Config(
        app=AppConfig(name="ANIE", environment="test"),
        model=ModelConfig(
            provider="ollama",
            model="qwen3:1.7b",
            base_url="http://localhost:11434",
            timeout_seconds=5.0,
        ),
        runtime=RuntimeConfig(log_level="INFO"),
    )


@pytest.fixture
def valid_config_with_fallback(valid_config: Config) -> Config:
    return Config(
        app=valid_config.app,
        model=valid_config.model,
        runtime=valid_config.runtime,
        fallback=ModelConfig(
            provider="nvidia",
            model="meta/llama-3.1-8b-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout_seconds=5.0,
            api_key_env="NVIDIA_API_KEY",
        ),
    )


class FakeRouter:
    """Stand-in for ModelRouter that just returns pre-built provider(s).

    `fallback_provider` defaults to None, matching Phase 0 behavior (no
    fallback configured). Agent treats a router with no
    `get_fallback_provider` method, or one that returns None, identically.
    """

    def __init__(
        self, provider: ModelProvider, fallback_provider: Optional[ModelProvider] = None
    ):
        self._provider = provider
        self._fallback_provider = fallback_provider

    def get_provider(self) -> ModelProvider:
        return self._provider

    def get_fallback_provider(self) -> Optional[ModelProvider]:
        return self._fallback_provider


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def fake_fallback_provider() -> FakeProvider:
    return FakeProvider(response="fallback response")


@pytest.fixture
def fake_router(fake_provider: FakeProvider) -> FakeRouter:
    return FakeRouter(fake_provider)


@pytest.fixture
def fake_router_with_fallback(
    fake_provider: FakeProvider, fake_fallback_provider: FakeProvider
) -> FakeRouter:
    return FakeRouter(fake_provider, fallback_provider=fake_fallback_provider)
