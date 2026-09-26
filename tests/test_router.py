from __future__ import annotations

import pytest

from app.core.config import AppConfig, Config, ModelConfig, RuntimeConfig
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
