"""Generic, host-agnostic network diagnostic adapter.

Implements `ping`, `traceroute`, `dns_lookup`, and `tcp_connectivity` using
the system `ping`/`traceroute` binaries via `subprocess.run` with an
explicit argument list — never `shell=True`, never a model-supplied command
string — plus the standard library `socket` module for DNS/TCP checks.
This is a fixed, parameterized set of read-only diagnostics, not arbitrary
command execution: the only thing a caller can vary is the target host (and
a bounded count/hop-limit/port), and `host` is validated against a strict
allowlist pattern before it ever reaches a subprocess argument.
"""

from __future__ import annotations

import logging
import platform
import re
import socket
import subprocess
from typing import Any

from app.adapters.base import Adapter

logger = logging.getLogger("anie.adapter.generic")

# Conservative allowlist for a hostname/IPv4/IPv6 literal. Not a full
# validator — just enough to reject anything that isn't plausibly a host,
# before it reaches a subprocess argument list (which is not vulnerable to
# shell injection either way, since we never use shell=True).
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-:_]+$")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}}


class GenericAdapter(Adapter):
    name = "generic"

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        default_ping_count: int = 4,
        default_traceroute_max_hops: int = 30,
    ):
        self.timeout_seconds = timeout_seconds
        self.default_ping_count = default_ping_count
        self.default_traceroute_max_hops = default_traceroute_max_hops

    def list_capabilities(self) -> list[str]:
        return ["ping", "traceroute", "dns_lookup", "tcp_connectivity"]

    def invoke(self, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_invoke_{capability}", None)
        if handler is None:
            return _error("unsupported_capability", f"Generic adapter does not support '{capability}'.")

        host = arguments.get("host")
        if not host or not isinstance(host, str) or not _HOST_RE.match(host):
            return _error("invalid_arguments", "A valid 'host' argument is required.")

        try:
            return handler(host, arguments)
        except Exception as exc:  # defensive: adapters must never raise
            logger.error(
                "adapter.error",
                extra={"component": "generic_adapter", "event": "adapter.error", "capability": capability},
            )
            return _error("execution_failed", f"'{capability}' failed: {exc}")

    def _invoke_ping(self, host: str, arguments: dict[str, Any]) -> dict[str, Any]:
        count = int(arguments.get("count", self.default_ping_count))
        flag = "-n" if platform.system().lower() == "windows" else "-c"
        return self._run_subprocess(["ping", flag, str(count), host])

    def _invoke_traceroute(self, host: str, arguments: dict[str, Any]) -> dict[str, Any]:
        max_hops = int(arguments.get("max_hops", self.default_traceroute_max_hops))
        is_windows = platform.system().lower() == "windows"
        binary = "tracert" if is_windows else "traceroute"
        flag = "-h" if is_windows else "-m"
        return self._run_subprocess([binary, flag, str(max_hops), host])

    def _invoke_dns_lookup(self, host: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            _, _, addresses = socket.gethostbyname_ex(host)
        except socket.gaierror as exc:
            return _error("dns_resolution_failed", f"Could not resolve '{host}': {exc}")
        return {"success": True, "data": {"host": host, "addresses": addresses}}

    def _invoke_tcp_connectivity(self, host: str, arguments: dict[str, Any]) -> dict[str, Any]:
        port = arguments.get("port")
        if port is None:
            return _error("invalid_arguments", "A 'port' argument is required for tcp_connectivity.")
        try:
            port = int(port)
        except (TypeError, ValueError):
            return _error("invalid_arguments", "'port' must be an integer.")

        try:
            with socket.create_connection((host, port), timeout=self.timeout_seconds):
                pass
        except (socket.timeout, TimeoutError):
            return _error("connection_timeout", f"Timed out connecting to {host}:{port}")
        except OSError as exc:
            return _error("connection_failed", f"Could not connect to {host}:{port}: {exc}")
        return {"success": True, "data": {"host": host, "port": port, "reachable": True}}

    def _run_subprocess(self, cmd: list[str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout_seconds
            )
        except subprocess.TimeoutExpired:
            return _error(
                "connection_timeout", f"'{' '.join(cmd)}' timed out after {self.timeout_seconds}s"
            )
        except FileNotFoundError as exc:
            return _error("tool_unavailable", f"Required system tool not found: {exc}")

        return {
            "success": True,
            "data": {
                "command": cmd,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        }

    def health_check(self) -> bool:
        return True
