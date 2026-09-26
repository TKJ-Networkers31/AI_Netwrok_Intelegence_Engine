from __future__ import annotations

import pytest

from app.core.config import AppConfig, Config, ModelConfig, RuntimeConfig
from app.models.providers.nvidia import NvidiaProvider
from app.models.providers.ollama import OllamaProvider
from app.models.router import ModelRouter, UnsupportedProviderError


def test_router_selects_configured_provider(valid_config):
    router = ModelRouter(valid_config)

    provider = router.get_provider()

    assert isinstance(provider, OllamaProvider)
    assert provider.model == valid_config.model.model
    assert provider.base_url == valid_config.model.base_url


def test_router_rejects_unsupported_provider(valid_config):
    bad_config = Config(
        app=valid_config.app,
        model=ModelConfig(
            provider="not-real",
            model="x",
            base_url="http://localhost:1",
        ),
        runtime=valid_config.runtime,
    )

    with pytest.raises(UnsupportedProviderError):
        ModelRouter(bad_config)


def test_router_has_no_fallback_when_not_configured(valid_config):
    router = ModelRouter(valid_config)

    assert router.has_fallback() is False
    assert router.get_fallback_provider() is None


def test_router_resolves_nvidia_fallback(valid_config_with_fallback):
    router = ModelRouter(valid_config_with_fallback)

    fallback = router.get_fallback_provider()

    assert router.has_fallback() is True
    assert isinstance(fallback, NvidiaProvider)
    assert fallback.model == valid_config_with_fallback.fallback.model
    assert fallback.base_url == valid_config_with_fallback.fallback.base_url
    assert fallback.api_key_env == "NVIDIA_API_KEY"
    # Primary provider resolution is unaffected by having a fallback.
    assert isinstance(router.get_provider(), OllamaProvider)


def test_router_rejects_unsupported_fallback_provider(valid_config):
    bad_config = Config(
        app=valid_config.app,
        model=valid_config.model,
        runtime=valid_config.runtime,
        fallback=ModelConfig(
            provider="not-real",
            model="x",
            base_url="http://localhost:1",
        ),
    )

    with pytest.raises(UnsupportedProviderError):
        ModelRouter(bad_config)
