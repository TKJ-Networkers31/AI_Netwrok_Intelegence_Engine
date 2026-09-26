"""Runnable MCP server process exposing generic (ping/traceroute/DNS/TCP)
capabilities. See `mikrotik_server.py` for the general pattern.

    mcp:
      servers:
        - name: generic
          transport: stdio
          command: python
          args: ["-m", "app.mcp.servers.generic_server"]
"""

from __future__ import annotations

import argparse
import sys

from app.adapters.generic import GenericAdapter
from app.capabilities.definitions import build_default_registry
from app.mcp.adapter_handler import AdapterToolHandler
from app.mcp.server import MCPServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anie-mcp-generic")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)

    adapter = GenericAdapter(timeout_seconds=args.timeout_seconds)
    registry = build_default_registry()
    handler = AdapterToolHandler(adapter, registry.for_server("generic"))
    MCPServer(handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
