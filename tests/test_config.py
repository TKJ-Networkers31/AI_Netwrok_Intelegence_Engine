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


VALID_CONFIG_WITH_FALLBACK = {
    "app": {"name": "ANIE", "environment": "test"},
    "model": {
        "primary": {
            "provider": "ollama",
            "model": "qwen3:1.7b",
            "base_url": "http://localhost:11434",
            "timeout_seconds": 30,
        },
        "fallback": {
            "provider": "nvidia",
            "model": "meta/llama-3.1-8b-instruct",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key_env": "NVIDIA_API_KEY",
            "timeout_seconds": 15,
        },
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
    assert config.fallback is None


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


# --- Phase 1: fallback / NVIDIA config tests ---------------------------------


def test_no_fallback_section_means_no_fallback(tmp_path):
    path = _write_config(tmp_path, VALID_CONFIG)

    config = Config.load(path)

    assert config.fallback is None


def test_fallback_section_loads(tmp_path):
    path = _write_config(tmp_path, VALID_CONFIG_WITH_FALLBACK)

    config = Config.load(path)

    assert config.fallback is not None
    assert config.fallback.provider == "nvidia"
    assert config.fallback.model == "meta/llama-3.1-8b-instruct"
    assert config.fallback.base_url == "https://integrate.api.nvidia.com/v1"
    assert config.fallback.api_key_env == "NVIDIA_API_KEY"
    assert config.fallback.timeout_seconds == 15


def test_fallback_unsupported_provider_fails_clearly(tmp_path):
    data = dict(VALID_CONFIG)
    data["model"] = dict(VALID_CONFIG["model"])
    data["model"]["fallback"] = {
        "provider": "not-real",
        "model": "x",
        "base_url": "http://localhost:1",
    }
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="Unsupported model provider"):
        Config.load(path)


def test_fallback_missing_model_fails_clearly(tmp_path):
    data = dict(VALID_CONFIG)
    data["model"] = dict(VALID_CONFIG["model"])
    data["model"]["fallback"] = {
        "provider": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
    }
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="model.fallback.model"):
        Config.load(path)


def test_nvidia_fallback_defaults_base_url_and_api_key_env(tmp_path):
    data = dict(VALID_CONFIG)
    data["model"] = dict(VALID_CONFIG["model"])
    data["model"]["fallback"] = {
        "provider": "nvidia",
        "model": "meta/llama-3.1-8b-instruct",
    }
    path = _write_config(tmp_path, data)

    config = Config.load(path)

    assert config.fallback.base_url == "https://integrate.api.nvidia.com/v1"
    assert config.fallback.api_key_env == "NVIDIA_API_KEY"


def test_shared_model_timeout_applies_to_both_sections(tmp_path):
    data = dict(VALID_CONFIG)
    data["model"] = {
        "primary": {
            "provider": "ollama",
            "model": "qwen3:1.7b",
            "base_url": "http://localhost:11434",
        },
        "fallback": {
            "provider": "nvidia",
            "model": "meta/llama-3.1-8b-instruct",
        },
        "timeout": 45,
    }
    path = _write_config(tmp_path, data)

    config = Config.load(path)

    assert config.model.timeout_seconds == 45
    assert config.fallback.timeout_seconds == 45


def test_fallback_env_overrides_enable_fallback_without_yaml_section(tmp_path, monkeypatch):
    path = _write_config(tmp_path, VALID_CONFIG)
    monkeypatch.setenv("ANIE_FALLBACK_PROVIDER", "nvidia")
    monkeypatch.setenv("ANIE_FALLBACK_MODEL", "meta/llama-3.1-8b-instruct")

    config = Config.load(path)

    assert config.fallback is not None
    assert config.fallback.provider == "nvidia"
    assert config.fallback.model == "meta/llama-3.1-8b-instruct"


def test_no_api_key_read_into_config(tmp_path, monkeypatch):
    """The API key value itself must never end up in the parsed Config."""
    path = _write_config(tmp_path, VALID_CONFIG_WITH_FALLBACK)
    monkeypatch.setenv("NVIDIA_API_KEY", "super-secret-value")

    config = Config.load(path)

    assert config.fallback.api_key_env == "NVIDIA_API_KEY"
    assert "super-secret-value" not in repr(config)


# --- Phase 2: MCP server config tests ----------------------------------------


def test_no_mcp_section_means_no_servers(tmp_path):
    path = _write_config(tmp_path, VALID_CONFIG)

    config = Config.load(path)

    assert config.mcp.servers == ()


def test_mcp_servers_section_loads(tmp_path):
    data = dict(VALID_CONFIG)
    data["mcp"] = {
        "servers": [
            {
                "name": "mikrotik",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "app.mcp.servers.mikrotik_server", "--host", "10.0.0.1"],
                "timeout_seconds": 20,
            },
            {
                "name": "generic",
                "command": "python",
                "args": ["-m", "app.mcp.servers.generic_server"],
            },
        ]
    }
    path = _write_config(tmp_path, data)

    config = Config.load(path)

    assert len(config.mcp.servers) == 2
    mikrotik = config.mcp.servers[0]
    assert mikrotik.name == "mikrotik"
    assert mikrotik.transport == "stdio"
    assert mikrotik.command == "python"
    assert mikrotik.args == ("-m", "app.mcp.servers.mikrotik_server", "--host", "10.0.0.1")
    assert mikrotik.timeout_seconds == 20

    generic = config.mcp.servers[1]
    assert generic.transport == "stdio"  # default
    assert generic.timeout_seconds == 15.0  # default


def test_mcp_server_missing_name_fails_clearly(tmp_path):
    data = dict(VALID_CONFIG)
    data["mcp"] = {"servers": [{"command": "python"}]}
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="mcp.servers\\[\\].name"):
        Config.load(path)


def test_mcp_server_missing_command_fails_clearly(tmp_path):
    data = dict(VALID_CONFIG)
    data["mcp"] = {"servers": [{"name": "mikrotik"}]}
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="command"):
        Config.load(path)


def test_mcp_server_unsupported_transport_fails_clearly(tmp_path):
    data = dict(VALID_CONFIG)
    data["mcp"] = {"servers": [{"name": "mikrotik", "transport": "http", "command": "x"}]}
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="Unsupported MCP transport"):
        Config.load(path)


def test_mcp_server_invalid_timeout_fails_clearly(tmp_path):
    data = dict(VALID_CONFIG)
    data["mcp"] = {
        "servers": [{"name": "mikrotik", "command": "x", "timeout_seconds": "nope"}]
    }
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="timeout_seconds"):
        Config.load(path)


def test_no_mcp_credentials_read_into_config(tmp_path, monkeypatch):
    """MikroTik (or any adapter) credentials must never end up in Config —
    they are read directly by the adapter process from the environment."""
    data = dict(VALID_CONFIG)
    data["mcp"] = {
        "servers": [{"name": "mikrotik", "command": "python", "args": ["-m", "x"]}]
    }
    path = _write_config(tmp_path, data)
    monkeypatch.setenv("MIKROTIK_PASSWORD", "super-secret-password")

    config = Config.load(path)

    assert "super-secret-password" not in repr(config)
