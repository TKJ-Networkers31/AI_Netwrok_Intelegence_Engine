from __future__ import annotations

import socket
import subprocess
from unittest.mock import MagicMock, patch

from app.adapters.generic import GenericAdapter


def make_adapter(**kwargs) -> GenericAdapter:
    return GenericAdapter(timeout_seconds=2.0, **kwargs)


def test_invoke_rejects_missing_host():
    adapter = make_adapter()

    result = adapter.invoke("ping", {})

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_arguments"


def test_invoke_rejects_invalid_host_characters():
    adapter = make_adapter()

    result = adapter.invoke("ping", {"host": "10.0.0.1; rm -rf /"})

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_arguments"


def test_invoke_unsupported_capability():
    adapter = make_adapter()

    result = adapter.invoke("not_a_real_capability", {"host": "10.0.0.1"})

    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_capability"


@patch("app.adapters.generic.subprocess.run")
def test_ping_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=["ping"], returncode=0, stdout="4 packets transmitted", stderr=""
    )
    adapter = make_adapter()

    result = adapter.invoke("ping", {"host": "10.0.0.1", "count": 2})

    assert result["success"] is True
    assert result["data"]["exit_code"] == 0
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ping"
    assert "10.0.0.1" in cmd
    assert "2" in cmd


@patch("app.adapters.generic.subprocess.run")
def test_ping_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ping", timeout=2.0)
    adapter = make_adapter()

    result = adapter.invoke("ping", {"host": "10.0.0.1"})

    assert result["success"] is False
    assert result["error"]["code"] == "connection_timeout"


@patch("app.adapters.generic.subprocess.run")
def test_ping_tool_missing(mock_run):
    mock_run.side_effect = FileNotFoundError("ping not found")
    adapter = make_adapter()

    result = adapter.invoke("ping", {"host": "10.0.0.1"})

    assert result["success"] is False
    assert result["error"]["code"] == "tool_unavailable"


@patch("app.adapters.generic.subprocess.run")
def test_traceroute_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=["traceroute"], returncode=0, stdout="1 10.0.0.1", stderr=""
    )
    adapter = make_adapter()

    result = adapter.invoke("traceroute", {"host": "10.0.0.1", "max_hops": 5})

    assert result["success"] is True
    cmd = mock_run.call_args[0][0]
    assert "5" in cmd


@patch("app.adapters.generic.socket.gethostbyname_ex")
def test_dns_lookup_success(mock_resolve):
    mock_resolve.return_value = ("example.com", [], ["93.184.216.34"])
    adapter = make_adapter()

    result = adapter.invoke("dns_lookup", {"host": "example.com"})

    assert result["success"] is True
    assert result["data"]["addresses"] == ["93.184.216.34"]


@patch("app.adapters.generic.socket.gethostbyname_ex")
def test_dns_lookup_failure(mock_resolve):
    mock_resolve.side_effect = socket.gaierror("not found")
    adapter = make_adapter()

    result = adapter.invoke("dns_lookup", {"host": "nonexistent.invalid"})

    assert result["success"] is False
    assert result["error"]["code"] == "dns_resolution_failed"


def test_tcp_connectivity_missing_port():
    adapter = make_adapter()

    result = adapter.invoke("tcp_connectivity", {"host": "10.0.0.1"})

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_arguments"


@patch("app.adapters.generic.socket.create_connection")
def test_tcp_connectivity_success(mock_connect):
    mock_connect.return_value.__enter__ = MagicMock()
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)
    adapter = make_adapter()

    result = adapter.invoke("tcp_connectivity", {"host": "10.0.0.1", "port": 22})

    assert result["success"] is True
    assert result["data"]["reachable"] is True


@patch("app.adapters.generic.socket.create_connection")
def test_tcp_connectivity_refused(mock_connect):
    mock_connect.side_effect = ConnectionRefusedError("refused")
    adapter = make_adapter()

    result = adapter.invoke("tcp_connectivity", {"host": "10.0.0.1", "port": 22})

    assert result["success"] is False
    assert result["error"]["code"] == "connection_failed"


@patch("app.adapters.generic.socket.create_connection")
def test_tcp_connectivity_timeout(mock_connect):
    mock_connect.side_effect = socket.timeout("slow")
    adapter = make_adapter()

    result = adapter.invoke("tcp_connectivity", {"host": "10.0.0.1", "port": 22})

    assert result["success"] is False
    assert result["error"]["code"] == "connection_timeout"


def test_health_check_true():
    adapter = make_adapter()

    assert adapter.health_check() is True
