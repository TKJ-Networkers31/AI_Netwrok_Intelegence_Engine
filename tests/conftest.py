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


class FakeRouter:
    """Stand-in for ModelRouter that just returns a pre-built provider."""

    def __init__(self, provider: ModelProvider):
        self._provider = provider

    def get_provider(self) -> ModelProvider:
        return self._provider


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def fake_router(fake_provider: FakeProvider) -> FakeRouter:
    return FakeRouter(fake_provider)
