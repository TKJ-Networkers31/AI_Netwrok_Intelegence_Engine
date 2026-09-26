"""ModelRouter: selects the configured model provider(s).

Phase 0 scope was a single primary provider, no fallback, no load
balancing, no capability matching.

Phase 1 adds an optional fallback provider: the router still resolves a
single primary provider eagerly (via `get_provider()`, unchanged from
Phase 0), and additionally resolves an optional fallback provider (via
`get_fallback_provider()`) when `config.fallback` is set. Routing stays
deterministic — the Agent tries the primary provider first and only calls
the fallback provider when the primary's `generate()` call fails; there is
no load balancing or capability-based selection.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import Config, ModelConfig
from app.models.base import ModelProvider
from app.models.providers.nvidia import DEFAULT_API_KEY_ENV as _DEFAULT_NVIDIA_API_KEY_ENV
from app.models.providers.nvidia import NvidiaProvider
from app.models.providers.ollama import OllamaProvider


class UnsupportedProviderError(Exception):
    """Raised when the configured provider is not recognized."""


_PROVIDER_FACTORIES = {
    "ollama": lambda model_config: OllamaProvider(
        model=model_config.model,
        base_url=model_config.base_url,
        timeout_seconds=model_config.timeout_seconds,
    ),
    "nvidia": lambda model_config: NvidiaProvider(
        model=model_config.model,
        base_url=model_config.base_url,
        timeout_seconds=model_config.timeout_seconds,
        api_key_env=model_config.api_key_env or _DEFAULT_NVIDIA_API_KEY_ENV,
    ),
}


class ModelRouter:
    """Resolves the configured primary (and optional fallback) provider.

    Both providers are resolved eagerly at construction time, matching
    Phase 0's "fail fast on bad configuration" behavior — an unsupported
    provider name raises `UnsupportedProviderError` immediately rather than
    on the first request.
    """

    def __init__(self, config: Config):
        self._provider = self._build_provider(config.model, "model.primary")
        self._fallback_provider: Optional[ModelProvider] = None
        if config.fallback is not None:
            self._fallback_provider = self._build_provider(
                config.fallback, "model.fallback"
            )

    def get_provider(self) -> ModelProvider:
        """Return the primary provider (Phase 0 behavior, unchanged)."""
        return self._provider

    def get_fallback_provider(self) -> Optional[ModelProvider]:
        """Return the fallback provider, or None if none is configured."""
        return self._fallback_provider

    def has_fallback(self) -> bool:
        return self._fallback_provider is not None

    @staticmethod
    def _build_provider(model_config: ModelConfig, section_name: str) -> ModelProvider:
        provider_name = model_config.provider
        factory = _PROVIDER_FACTORIES.get(provider_name)
        if factory is None:
            raise UnsupportedProviderError(
                f"No provider registered for '{provider_name}' ({section_name}). "
                f"Supported: {sorted(_PROVIDER_FACTORIES)}"
            )
        return factory(model_config)
