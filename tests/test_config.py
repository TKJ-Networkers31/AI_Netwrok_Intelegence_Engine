from __future__ import annotations

import os

import pytest
import yaml

from app.core.config import Config, ConfigError


def _write_config(tmp_path, data: dict) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return str(path)


VALID_CONFIG = {
    "app": {"name": "ANIE", "environment": "test"},
    "model": {
        "primary": {
            "provider": "ollama",
            "model": "qwen3:1.7b",
            "base_url": "http://localhost:11434",
            "timeout_seconds": 30,
        }
    },
    "runtime": {"log_level": "DEBUG"},
}


def test_valid_config_loads(tmp_path):
    path = _write_config(tmp_path, VALID_CONFIG)

    config = Config.load(path)

    assert config.app.name == "ANIE"
    assert config.model.provider == "ollama"
    assert config.model.model == "qwen3:1.7b"
    assert config.model.base_url == "http://localhost:11434"
    assert config.model.timeout_seconds == 30
    assert config.runtime.log_level == "DEBUG"


def test_missing_file_fails_clearly(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.yaml")

    with pytest.raises(ConfigError, match="not found"):
        Config.load(missing_path)


def test_missing_provider_fails_clearly(tmp_path):
    data = {
        "model": {"primary": {"model": "qwen3:1.7b", "base_url": "http://localhost:11434"}}
    }
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="provider"):
        Config.load(path)


def test_unsupported_provider_fails_clearly(tmp_path):
    data = {
        "model": {
            "primary": {
                "provider": "not-a-real-provider",
                "model": "qwen3:1.7b",
                "base_url": "http://localhost:11434",
            }
        }
    }
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="Unsupported model provider"):
        Config.load(path)


def test_missing_model_name_fails_clearly(tmp_path):
    data = {
        "model": {"primary": {"provider": "ollama", "base_url": "http://localhost:11434"}}
    }
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="model.primary.model"):
        Config.load(path)


def test_invalid_timeout_fails_clearly(tmp_path):
    data = dict(VALID_CONFIG)
    data["model"] = {
        "primary": {
            "provider": "ollama",
            "model": "qwen3:1.7b",
            "base_url": "http://localhost:11434",
            "timeout_seconds": "not-a-number",
        }
    }
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="timeout_seconds"):
        Config.load(path)


def test_invalid_yaml_fails_clearly(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("app: [this is not\n  valid: yaml")

    with pytest.raises(ConfigError, match="not valid YAML"):
        Config.load(str(path))


def test_env_override_applies(tmp_path, monkeypatch):
    path = _write_config(tmp_path, VALID_CONFIG)
    monkeypatch.setenv("ANIE_MODEL_BASE_URL", "http://example.com:1234")
    monkeypatch.setenv("ANIE_LOG_LEVEL", "WARNING")

    config = Config.load(path)

    assert config.model.base_url == "http://example.com:1234"
    assert config.runtime.log_level == "WARNING"
