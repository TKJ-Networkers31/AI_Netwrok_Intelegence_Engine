from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from app.adapters.mikrotik import MikroTikAdapter


def make_adapter(**kwargs) -> MikroTikAdapter:
    return MikroTikAdapter(host="10.0.0.1", timeout_seconds=5.0, **kwargs)


def test_list_capabilities_are_namespaced():
    adapter = make_adapter()

    capabilities = adapter.list_capabilities()

    assert "mikrotik_get_interfaces" in capabilities
    assert all(c.startswith("mikrotik_") for c in capabilities)


def test_invoke_missing_credentials_fails_without_network_call():
    adapter = make_adapter()

    with patch("app.adapters.mikrotik.requests.get") as mock_get:
        result = adapter.invoke("mikrotik_get_interfaces", {})

    assert result["success"] is False
    assert result["error"]["code"] == "authentication_failed"
    mock_get.assert_not_called()


@patch("app.adapters.mikrotik.requests.get")
def test_invoke_success(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"name": "ether1"}]
    mock_get.return_value = mock_response

    adapter = make_adapter()
    result = adapter.invoke("mikrotik_get_interfaces", {})

    assert result["success"] is True
    assert result["data"]["items"] == [{"name": "ether1"}]
    _, kwargs = mock_get.call_args
    assert kwargs["auth"] == ("admin", "secret")
    assert "interface" in mock_get.call_args[0][0]


def test_invoke_unsupported_capability():
    adapter = make_adapter()

    result = adapter.invoke("mikrotik_get_nonexistent", {})

    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_capability"


@patch("app.adapters.mikrotik.requests.get")
def test_invoke_authentication_failure(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "wrong")
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_get.return_value = mock_response

    adapter = make_adapter()
    result = adapter.invoke("mikrotik_get_interfaces", {})

    assert result["success"] is False
    assert result["error"]["code"] == "authentication_failed"
    assert "wrong" not in result["error"]["message"]


@patch("app.adapters.mikrotik.requests.get")
def test_invoke_timeout(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    mock_get.side_effect = requests.exceptions.Timeout()

    adapter = make_adapter()
    result = adapter.invoke("mikrotik_get_routes", {})

    assert result["success"] is False
    assert result["error"]["code"] == "connection_timeout"


@patch("app.adapters.mikrotik.requests.get")
def test_invoke_connection_error(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    mock_get.side_effect = requests.exceptions.ConnectionError("refused")

    adapter = make_adapter()
    result = adapter.invoke("mikrotik_get_routes", {})

    assert result["success"] is False
    assert result["error"]["code"] == "connection_failed"


@patch("app.adapters.mikrotik.requests.get")
def test_invoke_not_found(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    adapter = make_adapter()
    result = adapter.invoke("mikrotik_get_dhcp", {})

    assert result["success"] is False
    assert result["error"]["code"] == "not_found"


@patch("app.adapters.mikrotik.requests.get")
def test_invoke_server_error(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "internal error"
    mock_get.return_value = mock_response

    adapter = make_adapter()
    result = adapter.invoke("mikrotik_get_firewall", {})

    assert result["success"] is False
    assert result["error"]["code"] == "connection_failed"


@patch("app.adapters.mikrotik.requests.get")
def test_invoke_malformed_response(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("not json")
    mock_get.return_value = mock_response

    adapter = make_adapter()
    result = adapter.invoke("mikrotik_get_dns", {})

    assert result["success"] is False
    assert result["error"]["code"] == "malformed_response"


def test_health_check_false_without_credentials():
    adapter = make_adapter()

    assert adapter.health_check() is False


@patch("app.adapters.mikrotik.requests.get")
def test_health_check_true(mock_get, monkeypatch):
    monkeypatch.setenv("MIKROTIK_USERNAME", "admin")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    adapter = make_adapter()

    assert adapter.health_check() is True
