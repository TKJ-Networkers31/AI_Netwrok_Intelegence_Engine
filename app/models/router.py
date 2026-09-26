"""ModelRouter: selects the configured model provider.

Phase 0 scope: a single primary provider, no fallback, no load balancing,
no capability matching. The abstraction is kept so future phases can extend
routing logic without changing how Agent uses the router.
"""

from __future__ import annotations

from app.core.config import Config
from app.models.base import ModelProvider
from app.models.providers.ollama import OllamaProvider


class UnsupportedProviderError(Exception):
    """Raised when the configured provider is not recognized."""


_PROVIDER_FACTORIES = {
    "ollama": lambda model_config: OllamaProvider(
        model=model_config.model,
        base_url=model_config.base_url,
        timeout_seconds=model_config.timeout_seconds,
    ),
}


class ModelRouter:
    """Resolves the configured primary provider on construction.

    Phase 0 always resolves eagerly to a single provider; `get_provider()`
    simply returns it. Keeping it as a method (rather than exposing the
    attribute directly) leaves room for future routing logic.
    """

    def __init__(self, config: Config):
        self._provider = self._build_provider(config)

    def get_provider(self) -> ModelProvider:
        return self._provider

    @staticmethod
    def _build_provider(config: Config) -> ModelProvider:
        provider_name = config.model.provider
        factory = _PROVIDER_FACTORIES.get(provider_name)
        if factory is None:
            raise UnsupportedProviderError(
                f"No provider registered for '{provider_name}'. "
                f"Supported: {sorted(_PROVIDER_FACTORIES)}"
            )
        return factory(config.model)
