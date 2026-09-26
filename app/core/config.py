"""Typed configuration for ANIE.

Configuration is loaded from a YAML file, with environment variables allowed
to override specific fields (mainly secrets / deployment-specific settings
that should not be committed to source control).

Phase 1 extends Phase 0's single `model.primary` section with an optional
`model.fallback` section (and a shared `model.timeout` default), so the
ModelRouter can fall back from Ollama to NVIDIA (or any other supported
provider) when the primary provider fails.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(Exception):
    """Raised when configuration is missing, malformed, or invalid."""


SUPPORTED_PROVIDERS = {"ollama", "nvidia"}

DEFAULT_TIMEOUT_SECONDS = 60.0

# NVIDIA-specific defaults. The API key itself is NEVER read from the config
# file or hardcoded here — only the *name* of the environment variable that
# holds it, so the actual secret always comes from the environment.
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_API_KEY_ENV = "NVIDIA_API_KEY"


@dataclass(frozen=True)
class AppConfig:
    name: str = "ANIE"
    environment: str = "development"


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    base_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    # Name of the environment variable holding this provider's API key, if
    # any (e.g. "NVIDIA_API_KEY"). Never the key value itself.
    api_key_env: Optional[str] = None


@dataclass(frozen=True)
class RuntimeConfig:
    log_level: str = "INFO"


@dataclass(frozen=True)
class Config:
    app: AppConfig
    model: ModelConfig
    runtime: RuntimeConfig
    # Optional fallback provider. None means Phase-0-style behavior: no
    # fallback configured, primary-only.
    fallback: Optional[ModelConfig] = None

    @staticmethod
    def load(path: Optional[str] = None) -> "Config":
        """Load configuration from a YAML file plus environment overrides.

        Args:
            path: Path to the YAML config file. Defaults to
                ``config/config.yaml`` relative to the project root, or the
                ``ANIE_CONFIG_PATH`` environment variable if set.

        Raises:
            ConfigError: if the file is missing, malformed, or fails
                validation.
        """
        config_path = _resolve_config_path(path)
        raw = _read_yaml(config_path)
        raw = _apply_env_overrides(raw)
        return _build_config(raw)


def _resolve_config_path(path: Optional[str]) -> Path:
    if path:
        return Path(path)
    env_path = os.environ.get("ANIE_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    # Default: <project_root>/config/config.yaml
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "config" / "config.yaml"


def _read_yaml(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Configuration file is not valid YAML: {exc}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError("Configuration file must define a top-level mapping.")
    return data


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides for secrets/deployment settings.

    Supported overrides:
        ANIE_CONFIG_PATH
        ANIE_MODEL_PROVIDER / ANIE_MODEL_NAME / ANIE_MODEL_BASE_URL /
            ANIE_MODEL_TIMEOUT_SECONDS               (model.primary.*)
        ANIE_FALLBACK_PROVIDER / ANIE_FALLBACK_MODEL / ANIE_FALLBACK_BASE_URL /
            ANIE_FALLBACK_TIMEOUT_SECONDS / ANIE_FALLBACK_API_KEY_ENV
                                                      (model.fallback.*)
        ANIE_MODEL_TIMEOUT                           (shared model.timeout)
        ANIE_LOG_LEVEL                                (runtime.log_level)

    Provider API keys themselves (e.g. NVIDIA_API_KEY) are never read here —
    providers read their own credential env vars directly at request time,
    so secrets never pass through the config dict.
    """
    raw = dict(raw)
    model = dict(raw.get("model", {}) or {})
    primary = dict(model.get("primary", {}) or {})
    fallback = dict(model.get("fallback", {}) or {})
    runtime = dict(raw.get("runtime", {}) or {})

    if "ANIE_MODEL_PROVIDER" in os.environ:
        primary["provider"] = os.environ["ANIE_MODEL_PROVIDER"]
    if "ANIE_MODEL_NAME" in os.environ:
        primary["model"] = os.environ["ANIE_MODEL_NAME"]
    if "ANIE_MODEL_BASE_URL" in os.environ:
        primary["base_url"] = os.environ["ANIE_MODEL_BASE_URL"]
    if "ANIE_MODEL_TIMEOUT_SECONDS" in os.environ:
        primary["timeout_seconds"] = os.environ["ANIE_MODEL_TIMEOUT_SECONDS"]

    if "ANIE_FALLBACK_PROVIDER" in os.environ:
        fallback["provider"] = os.environ["ANIE_FALLBACK_PROVIDER"]
    if "ANIE_FALLBACK_MODEL" in os.environ:
        fallback["model"] = os.environ["ANIE_FALLBACK_MODEL"]
    if "ANIE_FALLBACK_BASE_URL" in os.environ:
        fallback["base_url"] = os.environ["ANIE_FALLBACK_BASE_URL"]
    if "ANIE_FALLBACK_TIMEOUT_SECONDS" in os.environ:
        fallback["timeout_seconds"] = os.environ["ANIE_FALLBACK_TIMEOUT_SECONDS"]
    if "ANIE_FALLBACK_API_KEY_ENV" in os.environ:
        fallback["api_key_env"] = os.environ["ANIE_FALLBACK_API_KEY_ENV"]

    if "ANIE_MODEL_TIMEOUT" in os.environ:
        model["timeout"] = os.environ["ANIE_MODEL_TIMEOUT"]

    if "ANIE_LOG_LEVEL" in os.environ:
        runtime["log_level"] = os.environ["ANIE_LOG_LEVEL"]

    model["primary"] = primary
    # Only keep a fallback section if it actually has content (from the YAML
    # file and/or env overrides) — an empty section means "no fallback".
    if fallback:
        model["fallback"] = fallback
    raw["model"] = model
    raw["runtime"] = runtime
    return raw


def _build_model_config(section_name: str, section_raw: dict[str, Any], shared_timeout: Any) -> ModelConfig:
    """Build and validate a single provider section (primary or fallback).

    `section_name` is used purely for error messages (e.g. "model.primary").
    """
    provider = section_raw.get("provider")
    if not provider:
        raise ConfigError(f"{section_name}.provider is required")
    provider = str(provider)
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigError(
            f"Unsupported model provider '{provider}' in {section_name}. "
            f"Supported providers: {sorted(SUPPORTED_PROVIDERS)}"
        )

    model_name = section_raw.get("model")
    if not model_name:
        raise ConfigError(f"{section_name}.model is required")

    base_url = section_raw.get("base_url")
    if not base_url and provider == "nvidia":
        base_url = DEFAULT_NVIDIA_BASE_URL
    if not base_url:
        raise ConfigError(f"{section_name}.base_url is required")

    timeout_raw = section_raw.get(
        "timeout_seconds",
        shared_timeout if shared_timeout is not None else DEFAULT_TIMEOUT_SECONDS,
    )
    try:
        timeout_seconds = float(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"{section_name}.timeout_seconds must be a number, got: {timeout_raw!r}"
        ) from exc
    if timeout_seconds <= 0:
        raise ConfigError(f"{section_name}.timeout_seconds must be > 0")

    api_key_env = section_raw.get("api_key_env")
    if not api_key_env and provider == "nvidia":
        api_key_env = DEFAULT_NVIDIA_API_KEY_ENV

    return ModelConfig(
        provider=provider,
        model=str(model_name),
        base_url=str(base_url),
        timeout_seconds=timeout_seconds,
        api_key_env=str(api_key_env) if api_key_env else None,
    )


def _build_config(raw: dict[str, Any]) -> Config:
    app_raw = raw.get("app", {}) or {}
    model_raw = raw.get("model", {}) or {}
    primary_raw = model_raw.get("primary", {}) or {}
    fallback_raw = model_raw.get("fallback", {}) or {}
    runtime_raw = raw.get("runtime", {}) or {}

    app = AppConfig(
        name=str(app_raw.get("name", "ANIE")),
        environment=str(app_raw.get("environment", "development")),
    )

    shared_timeout = model_raw.get("timeout")

    model = _build_model_config("model.primary", primary_raw, shared_timeout)

    fallback: Optional[ModelConfig] = None
    if fallback_raw:
        fallback = _build_model_config("model.fallback", fallback_raw, shared_timeout)

    log_level = str(runtime_raw.get("log_level", "INFO")).upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level not in valid_levels:
        raise ConfigError(
            f"runtime.log_level must be one of {sorted(valid_levels)}, got: {log_level}"
        )
    runtime = RuntimeConfig(log_level=log_level)

    return Config(app=app, model=model, runtime=runtime, fallback=fallback)
