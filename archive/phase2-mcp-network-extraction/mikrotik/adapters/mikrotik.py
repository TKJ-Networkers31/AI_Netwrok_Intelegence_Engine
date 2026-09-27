"""MikroTik/RouterOS adapter.

Talks to a RouterOS device via its REST API (RouterOS v7+; see
https://help.mikrotik.com/docs/display/ROS/REST+API), reusing `requests`
exactly the way `OllamaProvider`/`NvidiaProvider` already do for their HTTP
APIs — no new runtime dependency, no SSH, no raw binary API protocol
(port 8728/8729), and no arbitrary command execution: each capability maps
to one fixed, read-only REST endpoint.

Credentials (username/password) are NEVER read from config.yaml — only the
*names* of the environment variables that hold them are configurable, and
the adapter reads them fresh from the environment on every call, the same
pattern `NvidiaProvider` uses for its API key.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

from app.adapters.base import Adapter

logger = logging.getLogger("anie.adapter.mikrotik")

DEFAULT_USERNAME_ENV = "MIKROTIK_USERNAME"
DEFAULT_PASSWORD_ENV = "MIKROTIK_PASSWORD"

# capability name -> RouterOS REST endpoint, relative to `<base>/rest/`.
_ENDPOINTS: dict[str, str] = {
    "mikrotik_get_interfaces": "interface",
    "mikrotik_get_ip_addresses": "ip/address",
    "mikrotik_get_routes": "ip/route",
    "mikrotik_get_arp": "ip/arp",
    "mikrotik_get_system_resources": "system/resource",
    "mikrotik_get_logs": "log",
    "mikrotik_get_dns": "ip/dns",
    "mikrotik_get_dhcp": "ip/dhcp-server/lease",
    "mikrotik_get_firewall": "ip/firewall/filter",
}


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}}


class MikroTikAdapter(Adapter):
    """`Adapter` implementation backed by a RouterOS device's REST API."""

    name = "mikrotik"

    def __init__(
        self,
        host: str,
        port: int = 443,
        use_tls: bool = True,
        username_env: str = DEFAULT_USERNAME_ENV,
        password_env: str = DEFAULT_PASSWORD_ENV,
        timeout_seconds: float = 15.0,
        verify_tls: bool = True,
    ):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.username_env = username_env or DEFAULT_USERNAME_ENV
        self.password_env = password_env or DEFAULT_PASSWORD_ENV
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls

    def list_capabilities(self) -> list[str]:
        return sorted(_ENDPOINTS)

    def _base_url(self) -> str:
        scheme = "https" if self.use_tls else "http"
        return f"{scheme}://{self.host}:{self.port}/rest"

    def _credentials(self) -> Optional[tuple[str, str]]:
        username = os.environ.get(self.username_env)
        password = os.environ.get(self.password_env)
        if not username or not password:
            return None
        return username, password

    def invoke(self, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        endpoint = _ENDPOINTS.get(capability)
        if endpoint is None:
            return _error("unsupported_capability", f"MikroTik adapter does not support '{capability}'.")

        credentials = self._credentials()
        if credentials is None:
            return _error(
                "authentication_failed",
                f"MikroTik credentials not set. Export {self.username_env} and "
                f"{self.password_env} before use.",
            )

        url = f"{self._base_url()}/{endpoint}"
        logger.info(
            "adapter.request",
            extra={
                "component": "mikrotik_adapter",
                "event": "adapter.request",
                "capability": capability,
                "url": url,
            },
        )

        try:
            response = requests.get(
                url, auth=credentials, timeout=self.timeout_seconds, verify=self.verify_tls
            )
        except requests.exceptions.Timeout:
            return _error(
                "connection_timeout",
                f"Timed out waiting for RouterOS at {self.host} after {self.timeout_seconds}s",
            )
        except requests.exceptions.ConnectionError as exc:
            return _error("connection_failed", f"Could not connect to RouterOS at {self.host}: {exc}")
        except requests.exceptions.RequestException as exc:
            return _error("request_failed", f"Request to RouterOS failed: {exc}")

        if response.status_code in (401, 403):
            return _error(
                "authentication_failed",
                f"RouterOS rejected the credentials (status {response.status_code}).",
            )
        if response.status_code == 404:
            return _error(
                "not_found",
                f"RouterOS endpoint '{endpoint}' was not found (status 404). "
                f"Check that this RouterOS version/build supports the REST API.",
            )
        if response.status_code >= 500:
            return _error(
                "connection_failed",
                f"RouterOS server error (status {response.status_code}): {response.text}",
            )
        if response.status_code >= 400:
            return _error(
                "request_failed",
                f"RouterOS rejected the request (status {response.status_code}): {response.text}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            return _error("malformed_response", f"RouterOS returned a non-JSON response: {exc}")

        logger.info(
            "adapter.response",
            extra={"component": "mikrotik_adapter", "event": "adapter.response", "capability": capability},
        )
        return {"success": True, "data": {"items": data}}

    def health_check(self) -> bool:
        credentials = self._credentials()
        if credentials is None:
            return False
        try:
            response = requests.get(
                f"{self._base_url()}/system/resource",
                auth=credentials,
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
