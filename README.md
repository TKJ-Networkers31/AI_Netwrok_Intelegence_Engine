# ANIE — Phase 2: MCP & Network Capability Layer

ANIE (AI Network Intelligence Engine) is a standalone network engineering AI
system.

**Phase 0** implemented the foundational architecture: a CLI that sends a
prompt through an Agent, a ModelRouter, and a single model provider.

**Phase 1** extended the model layer with automatic fallback between two
model providers (NVIDIA primary, Ollama fallback).

**Phase 2** (this phase) adds a secure, provider-independent MCP/tool layer
so the model can request real, read-only network data instead of guessing:

```text
User → ANIE Agent → Model → Tool Request → Capability Validation
                                                  │
                                                  ▼
                                          CapabilityExecutor
                                                  │
                                                  ▼
                                             MCP Client
                                                  │
                                          (stdio transport)
                                                  ▼
                                         MCP Server / Adapter
                                                  │
                                                  ▼
                                    Network (RouterOS REST API,
                                    system ping/traceroute, sockets)
                                                  │
                                                  ▼
                                         Structured Result
                                                  │
                                                  ▼
                                          Model → Response
```

This phase does **not** implement DIO/APCE, an inventory system, a
credential vault, a general read/write/execute framework, a scheduler,
automation, voice, a GUI, persistent memory, RAG, autonomous remediation,
multi-agent orchestration, or production deployment. It is deliberately
read-only: every registered capability lists network state, nothing
configures or changes it.

---

## What's new in Phase 2

- **MCP client** (`app/mcp/client.py`) — connect/disconnect, `discover_tools()`,
  `invoke_tool()`, with typed errors for timeouts, connection failures,
  malformed responses, and disconnects. Transport-independent
  (`app/mcp/transport.py`); only a stdio (subprocess) transport is
  implemented, but the client has no idea what's on the other end.
- **MCP server** (`app/mcp/server.py`) — a tiny newline-delimited-JSON
  request/response loop (`discover` / `invoke` / `ping`) that any Python
  process can run over stdio. `app/mcp/adapter_handler.py` bridges an
  `Adapter` into this shape.
- **Capability registry** (`app/capabilities/registry.py`,
  `app/capabilities/definitions.py`) — the allowlist. Every capability has a
  name, description, input/output schema, risk level, and permissions.
  Nothing outside this registry is ever invocable.
- **Execution boundary** (`app/capabilities/executor.py`) — registry lookup
  → schema validation (`app/capabilities/validation.py`) → risk/permission
  check (read-only only, in Phase 2) → MCP invocation → normalized
  `ToolResult`. This is the *only* path from a model's tool request to an
  MCP server.
- **MikroTik/RouterOS adapter** (`app/adapters/mikrotik.py`) — the first
  real target, talking to RouterOS's REST API (v7+) over HTTPS.
- **Generic adapter** (`app/adapters/generic.py`) — host-agnostic
  `ping`/`traceroute`/`dns_lookup`/`tcp_connectivity`, using the system
  `ping`/`traceroute` binaries (fixed argument list, never `shell=True`)
  and the standard library `socket` module.
- **Linux adapter** (`app/adapters/linux.py`) — a placeholder, per the
  brief: capabilities are registered so the model/registry shape is
  complete, but every call returns a structured `not_implemented` error
  rather than fabricating data.
- **Agent tool-calling loop** (`app/core/agent.py`) — bounded (default 3
  iterations): if a provider requests tool calls, the Agent executes them
  through the boundary above, feeds the results back into the `Context`,
  and re-prompts the model. This is *not* autonomous multi-step planning —
  just "ask → tool → ask again", capped so it can't loop forever.
- **Config** (`app/core/config.py`) — an optional `mcp.servers` section.
  Credentials for adapters (e.g. MikroTik) are never read from YAML — only
  the environment variable *names* are configurable, exactly like the
  Phase 1 `NVIDIA_API_KEY` pattern.

Nothing about Phase 0/1 changed from the outside: `ModelProvider.generate(context) -> ExecutionResult`
is untouched, `Context`/`ExecutionResult` only gained new *optional* fields
(`Context.tools`, `ExecutionResult.tool_calls`), and an `Agent` built
without a `tool_executor` (the default) behaves exactly like Phase 1.

---

## Installation

Same as Phase 1 — no new runtime dependencies were added (the MikroTik
adapter reuses `requests`; the generic adapter uses only the standard
library).

```bash
cd anie
./setup.sh          # or setup.ps1 on Windows
# or: pip install -e ".[dev]"
```

## Setting up MikroTik (optional)

1. Enable the REST API on your RouterOS device (RouterOS 7.1+; typically
   already on if `www-ssl`/`www` services are enabled — see MikroTik's
   [REST API docs](https://help.mikrotik.com/docs/display/ROS/REST+API)).
2. Export credentials as environment variables (never put these in
   `config.yaml`):

```bash
export MIKROTIK_USERNAME=admin
export MIKROTIK_PASSWORD=change-me
```

3. Uncomment and edit the `mcp.servers` section in `config/config.yaml`
   (see below).

Without this, ANIE runs exactly as it did in Phase 1 — no tools available
to the model at all.

---

## Configuration

```yaml
mcp:
  servers:
    - name: mikrotik
      transport: stdio
      command: python
      args: ["-m", "app.mcp.servers.mikrotik_server", "--host", "10.0.0.1"]
      timeout_seconds: 15
    - name: generic
      transport: stdio
      command: python
      args: ["-m", "app.mcp.servers.generic_server"]
      timeout_seconds: 10
```

- `mcp.servers` is optional and defaults to empty — omitting it (or every
  server failing to connect) means the Agent gets no `tool_executor` and
  behaves exactly like Phase 1.
- `transport` only supports `stdio` today; `command`/`args` describe how
  ANIE launches that server as a subprocess.
- A server that fails to connect at startup is skipped (logged as a
  warning) rather than preventing ANIE from starting — capabilities routed
  to it simply fail with a `server_unavailable` error at request time.
- `--host`/`--port`/`--no-tls`/`--insecure`/`--username-env`/
  `--password-env` on `mikrotik_server` let you point at a specific device
  without touching credentials; see `python -m app.mcp.servers.mikrotik_server --help`.

Credentials (`MIKROTIK_USERNAME`/`MIKROTIK_PASSWORD` by default) are read
directly by the `mikrotik_server` process from the environment at request
time — never from `config.yaml`, never logged, never in an error message.

---

## Capabilities

All capabilities below are `read_only` — Phase 2 registers nothing else,
and `CapabilityExecutor` refuses to execute anything that isn't.

| Capability | Server | Description |
|---|---|---|
| `mikrotik_get_interfaces` | mikrotik | List network interfaces |
| `mikrotik_get_ip_addresses` | mikrotik | List configured IP addresses |
| `mikrotik_get_routes` | mikrotik | List the IPv4 routing table |
| `mikrotik_get_arp` | mikrotik | List ARP table entries |
| `mikrotik_get_system_resources` | mikrotik | CPU/memory/uptime |
| `mikrotik_get_logs` | mikrotik | Recent log entries |
| `mikrotik_get_dns` | mikrotik | DNS configuration |
| `mikrotik_get_dhcp` | mikrotik | DHCP server leases |
| `mikrotik_get_firewall` | mikrotik | Firewall filter rules |
| `linux_get_*` (10 capabilities) | linux | **Placeholder** — registered, returns `not_implemented` |
| `ping` | generic | ICMP ping a host |
| `traceroute` | generic | Trace the network path to a host |
| `dns_lookup` | generic | Resolve a hostname |
| `tcp_connectivity` | generic | Check if a TCP port is reachable |

Capability names are namespaced (`mikrotik_`/`linux_`) wherever the spec's
per-vendor lists would otherwise collide (both list a `get_interfaces`,
`get_routes`, `get_dns`, `get_logs`) — a flat registry, and a model's
`tools` list, both need globally unique names.

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```

No external network, live RouterOS device, or live Ollama/NVIDIA endpoint
is required — every provider/adapter/MCP call is mocked or exercised
in-process. New in Phase 2:

- **MCP client** (`test_mcp_client.py`): connect/disconnect, tool discovery
  (incl. caching and malformed schemas), successful/erroring invocation,
  timeout, disconnection, malformed response, send failure.
- **MCP server** (`test_mcp_server.py`): `ping`/`discover`/`invoke`,
  unknown method, missing tool name, a handler that raises, malformed
  JSON input, multi-line `serve_forever`.
- **Capability registry** (`test_capability_registry.py`): register/get/
  duplicate rejection/listing/per-server filtering.
- **Validation** (`test_capability_validation.py`): required fields, type
  mismatches (including bool-vs-integer), additional-properties handling.
- **Capability executor** (`test_capability_executor.py`): unknown
  capability, invalid arguments, non-read-only rejection, no server
  connected, success, MCP-level failure, each MCP error type, and that
  `get_tool_definitions()` only exposes read-only capabilities.
- **MikroTik adapter** (`test_mikrotik_adapter.py`): success, missing
  credentials (no network call made), auth failure, timeout, connection
  error, 404, 5xx, malformed JSON, health check.
- **Generic adapter** (`test_generic_adapter.py`): invalid/missing host,
  unsupported capability, ping/traceroute success/timeout/missing binary,
  DNS success/failure, TCP success/refused/timeout.
- **Linux adapter placeholder** (`test_linux_adapter.py`): every
  capability returns `not_implemented` with no fabricated `data`.
- **Adapter/MCP-server bridge** (`test_adapter_handler.py`).
- **Agent tool loop** (`test_agent_tools.py`): executes a requested tool
  and returns the model's final response; surfaces a tool *error* back to
  the model instead of crashing; rejects an unregistered tool without ever
  reaching an MCP client; a `tool_executor`-less Agent ignores
  `tool_calls` entirely (Phase 1 behavior); the iteration cap is enforced.
- **Provider tool-calling passthrough** (`test_ollama_provider.py`,
  `test_nvidia_provider.py`): `context.tools` is forwarded, and a
  provider-native `tool_calls` response is parsed into `ToolCall`s instead
  of being treated as an empty/malformed text response.
- **MCP config** (`test_config.py`): `mcp.servers` parsing, missing
  name/command, unsupported transport, invalid timeout, and that no
  adapter credential ever ends up in a parsed `Config`.

All Phase 0/1 tests are unchanged and still pass, confirming no regression.

---

## Architecture

### Project layout (Phase 2 additions marked)

```text
anie/
├── app/
│   ├── core/
│   │   ├── agent.py            # + bounded tool-calling loop
│   │   ├── config.py           # + mcp.servers section
│   │   ├── logging_setup.py
│   │   └── types.py            # + ToolCall, Context.tools, ExecutionResult.tool_calls
│   ├── models/
│   │   ├── base.py
│   │   ├── router.py
│   │   └── providers/
│   │       ├── nvidia.py       # + tools passthrough / tool_calls parsing
│   │       └── ollama.py       # + tools passthrough / tool_calls parsing
│   ├── capabilities/            # NEW
│   │   ├── types.py             # CapabilityDefinition, RiskLevel
│   │   ├── registry.py          # CapabilityRegistry (the allowlist)
│   │   ├── validation.py        # minimal schema validation
│   │   ├── definitions.py       # the default Phase 2 capability set
│   │   └── executor.py          # CapabilityExecutor (the execution boundary)
│   ├── adapters/                # NEW
│   │   ├── base.py               # Adapter interface
│   │   ├── mikrotik.py           # RouterOS REST API adapter
│   │   ├── generic.py            # ping/traceroute/dns_lookup/tcp_connectivity
│   │   └── linux.py              # placeholder
│   ├── mcp/                     # NEW
│   │   ├── protocol.py           # MCPRequest/MCPResponse/ToolSchema
│   │   ├── transport.py          # Transport interface + StdioTransport
│   │   ├── client.py             # MCPClient
│   │   ├── server.py             # MCPServer (the request loop)
│   │   ├── adapter_handler.py    # Adapter -> ToolHandler bridge
│   │   ├── bootstrap.py          # config.mcp.servers -> CapabilityExecutor
│   │   ├── errors.py             # MCPError and subclasses
│   │   └── servers/
│   │       ├── mikrotik_server.py  # runnable MCP server process
│   │       └── generic_server.py   # runnable MCP server process
│   └── events/
│       └── bus.py
├── cli/
│   └── main.py                  # + wires build_capability_executor into Agent
├── config/
│   └── config.yaml              # + commented-out mcp.servers example
├── tests/                       # + ~110 new Phase 2 tests
├── .env.example                  # + MIKROTIK_USERNAME/PASSWORD
└── README.md
```

### Core contracts

- **`Transport`** (`app/mcp/transport.py`): a bidirectional,
  message-oriented channel (`connect`/`disconnect`/`send`/`receive`). Only
  `StdioTransport` (subprocess) is implemented; `MCPClient` depends only on
  this interface, so other transports can be added without touching the
  client or anything above it.
- **`MCPClient`** (`app/mcp/client.py`): `connect()`, `disconnect()`,
  `discover_tools()` (cached), `invoke_tool()`. Raises `MCPConnectionError`,
  `MCPTimeoutError`, `MCPMalformedResponseError`, `MCPDisconnectedError`, or
  `MCPNotConnectedError` for expected failure modes — never a raw,
  unstructured exception.
- **`MCPServer`** (`app/mcp/server.py`): the process-side counterpart.
  Speaks the same tiny protocol; wraps whatever `ToolHandler` it's given
  (in practice, an `AdapterToolHandler` around an `Adapter`).
- **`Adapter`** (`app/adapters/base.py`): `list_capabilities()` +
  `invoke(capability, arguments) -> {"success", "data"|"error"}`. Same
  "small interface, structured result, never raise for expected failures"
  shape as `ModelProvider`.
- **`CapabilityDefinition`** / **`CapabilityRegistry`**
  (`app/capabilities/types.py`, `registry.py`): the allowlist. A capability
  not registered here can never be invoked, full stop.
- **`CapabilityExecutor`** (`app/capabilities/executor.py`): the execution
  boundary — registry lookup, schema validation, risk-level check, MCP
  invocation, normalization into `ToolResult`. `get_tool_definitions()`
  produces the OpenAI-style `tools` array handed to a provider via
  `Context.tools`.
- **`Context.tools`** / **`ExecutionResult.tool_calls`**
  (`app/core/types.py`): the minimal tool-calling contract added to the
  existing `Context`/`ExecutionResult` shapes — no new method on
  `ModelProvider`, no breaking change to `generate()`.
- **`Agent`** (`app/core/agent.py`): unchanged fallback logic, refactored
  into `_generate_with_fallback()` so the new `_run_tool_loop()` can call it
  again for each additional turn. With no `tool_executor` configured
  (the default), behavior is byte-for-byte identical to Phase 1.

### Security boundary

Enforced, in order, by `CapabilityExecutor.execute()`:

1. **Allowlist** — `CapabilityRegistry.get()` must return a match; anything
   else is `unknown_capability`.
2. **Schema validation** — `validate_arguments()` checks required fields
   and top-level types before anything else runs; failures are
   `invalid_arguments` and never reach an MCP server.
3. **Risk/permission check** — only `RiskLevel.READ_ONLY` capabilities may
   execute; anything else is `permission_denied`. Phase 2 registers
   nothing else, so this is currently a defense-in-depth check against a
   future mistake, not a live branch.
4. **MCP invocation** — routed to the connected `MCPClient` for that
   capability's `server`; no client connected is `server_unavailable`.
5. **Normalization** — every outcome (success, MCP-level tool error,
   timeout, connection failure, malformed response) becomes the same
   `ToolResult` shape (`{"success", "tool", "data"|"error", "metadata"}`).

No capability accepts a shell command, SSH command, arbitrary HTTP request,
or arbitrary code as an argument — every capability's `input_schema`
declares a fixed, narrow argument set (usually just `host`, sometimes
`count`/`max_hops`/`port`). The generic adapter's `ping`/`traceroute` calls
`subprocess.run` with a hard-coded binary name and an explicit argument
list — never `shell=True`, never a caller-supplied command string.

### Logging

New Phase 2 events, following the existing `component`/`event`/`request_id`
structured-logging convention: `mcp.connect`, `mcp.disconnect`,
`mcp.connect_failed`, `model.tool_call`, `tool.invoke`,
`agent.fallback` (unchanged from Phase 1), plus `tool.rejected` at the
`CapabilityExecutor` layer for allowlist/validation/permission rejections.

---

## Remaining / Out of Scope

Per the Phase 2 brief, still not implemented (deferred to later phases):
DIO, APCE, an inventory system, a credential vault, a general
read/write/execute framework, a scheduler, event-driven automation, voice/
STT/TTS, a GUI/PWA, persistent memory, RAG, advanced autonomous network
reasoning/remediation, multi-agent orchestration, and production
deployment (Docker/systemd/etc.).

Additionally, and specific to this phase:

- **A real, live RouterOS device was not available in this environment.**
  The MikroTik adapter's REST calls are validated against mocked
  responses (success, auth failure, timeout, connection error, 404, 5xx,
  malformed JSON), and the exact same MCP client → subprocess MCP server →
  adapter → structured-result pipeline was verified end-to-end using the
  generic adapter (real DNS resolution, a real refused-TCP-connection
  probe) instead — see the "Validation" section of the final report. The
  architecture is identical for MikroTik; only live-device verification is
  outstanding.
- **The Linux adapter is a placeholder**, exactly as the brief allows —
  registered capabilities, `not_implemented` responses, no fabricated data.
- **Only the `stdio` MCP transport is implemented.** `Transport` is an
  abstract interface specifically so a socket-based or other transport can
  be added later without touching `MCPClient`, `CapabilityExecutor`, or the
  Agent.
- **The tool-calling loop is intentionally not autonomous reasoning.** It's
  a bounded (default 3 iterations) "ask → tool → ask again" loop, per the
  brief's "do NOT implement full autonomous reasoning."
