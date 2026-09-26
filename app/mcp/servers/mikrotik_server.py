"""Runnable MCP server process exposing MikroTik/RouterOS capabilities.

This is normally launched BY ANIE itself, over stdio, per a `mcp.servers[]`
entry in config.yaml — not run directly by end users:

    mcp:
      servers:
        - name: mikrotik
          transport: stdio
          command: python
          args: ["-m", "app.mcp.servers.mikrotik_server", "--host", "10.0.0.1"]

Credentials are never passed as CLI arguments or read from config — this
process reads them from the environment (MIKROTIK_USERNAME/
MIKROTIK_PASSWORD by default) at request time, same as every other
credential in ANIE.
"""

from __future__ import annotations

import argparse
import sys

from app.adapters.mikrotik import DEFAULT_PASSWORD_ENV, DEFAULT_USERNAME_ENV, MikroTikAdapter
from app.capabilities.definitions import build_default_registry
from app.mcp.adapter_handler import AdapterToolHandler
from app.mcp.server import MCPServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anie-mcp-mikrotik")
    parser.add_argument("--host", required=True, help="RouterOS device host/IP")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--no-tls", action="store_true", help="Use plain HTTP instead of HTTPS")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS certificate verification")
    parser.add_argument("--username-env", default=DEFAULT_USERNAME_ENV)
    parser.add_argument("--password-env", default=DEFAULT_PASSWORD_ENV)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)

    adapter = MikroTikAdapter(
        host=args.host,
        port=args.port,
        use_tls=not args.no_tls,
        username_env=args.username_env,
        password_env=args.password_env,
        timeout_seconds=args.timeout_seconds,
        verify_tls=not args.insecure,
    )
    registry = build_default_registry()
    handler = AdapterToolHandler(adapter, registry.for_server("mikrotik"))
    MCPServer(handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
