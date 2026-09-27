# phase2-mcp-network-extraction

This archive is a **migration/reference package**, not a production-ready
MCP server. It preserves the vendor-specific and custom-protocol
implementation code that was removed from ANIE's active source tree during
the "separate MCP network implementation from ANIE" phase, so it can be
reused as a starting point for standalone MCP-MikroTik / MCP-Network
server projects in a later phase.

See `../MANIFEST.md` (one directory up) for the full file-by-file
inventory, dependency notes, and known limitations.

Directory guide:

- `mikrotik/`         — RouterOS REST API adapter + its MCP server entrypoint + tests.
- `generic-network/`  — ping/traceroute/dns_lookup/tcp_connectivity adapter + entrypoint + tests.
- `linux/`            — placeholder Linux adapter (not implemented) + tests.
- `capability-layer/` — the custom protocol's server-side loop, the
  capability registry/validation/executor, and the `Adapter` base
  interface — the glue that tied all of the above together and to the
  custom (non-standard) MCP-like protocol.
- `configs/`          — the pre-extraction `config.yaml` `mcp.servers`
  example, preserved for reference.

None of this archive contains real credentials, API keys, tokens, or any
`.env` file — see the extraction report for the explicit secrets check.
