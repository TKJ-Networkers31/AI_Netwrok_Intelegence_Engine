# ANIE — MCP Host + MCP Client (network implementation extraction phase)

ANIE (AI Network Intelligence Engine) is a standalone network engineering AI
system.

**Phase 0** implemented the foundational architecture: a CLI that sends a
prompt through an Agent, a ModelRouter, and a single model provider.

**Phase 1** extended the model layer with automatic fallback between two
model providers (NVIDIA primary, Ollama fallback).

**Phase 2 (original)** added a custom, MCP-*like* tool layer plus
vendor-specific network execution directly inside ANIE: a hand-rolled
`discover`/`invoke`/`ping` protocol over newline-delimited JSON, a
capability registry/executor bridging that protocol to a model's tool
calls, and adapters that spoke to a MikroTik/RouterOS device, ran system
`ping`/`traceroute`, and a placeholder Linux adapter.

**This phase** changes that architecture. The previous Phase 2 MCP
implementation was a **prototype/custom tool protocol** — not the
standards-compliant Model Context Protocol — and vendor-specific network
execution does not belong inside ANIE's core. This phase:

- Identifies and extracts every MikroTik/RouterOS-specific, generic-network,
  and Linux-placeholder implementation, plus the custom capability
  registry/executor and MCP server-side scaffolding built around them, into
  `archive/phase2-mcp-network-extraction/` (a migration/reference package —
  see its `MANIFEST.md`).
- Leaves ANIE's core (Agent, model providers/router, config, events, CLI)
  untouched and fully functional.
- Leaves a small, generic MCP **Client**-side skeleton in place
  (`app/mcp/transport.py`, `protocol.py`, `client.py`, `errors.py`) as the
  starting point for ANIE becoming a real MCP Host + MCP Client in a
  future phase — nothing vendor-specific remains in it.
- Does **not** build the final MCP-MikroTik server. That is explicitly
  out of scope here; it is future work on a separate project, using the
  archived MikroTik adapter as a reference implementation.

## Architecture

### Before this phase

```text
ANIE
 ├── custom MCP protocol (discover/invoke/ping over stdio JSON)
 ├── capability registry + executor (hardcodes mikrotik_*/linux_* schemas)
 └── vendor adapters (MikroTik/RouterOS, generic ping/traceroute/dns/tcp,
     Linux placeholder) + their MCP server entrypoints
```

### After this phase

```text
ANIE
 ├── Agent / ModelRouter / providers / config / events / CLI   (unchanged)
 └── app/mcp/  (generic MCP Client skeleton: transport, protocol, client,
                errors — no server-side code, no vendor code)

archive/phase2-mcp-network-extraction/   (migration reference package)
 ├── mikrotik/          -> future standalone MCP-MikroTik server
 ├── generic-network/   -> future standalone MCP-Network server
 ├── linux/             -> future MCP-Network or MCP-Linux server
 └── capability-layer/  -> reference only (custom protocol's server-side
                            loop + the registry/executor that hardcoded
                            vendor capability schemas)
```

### Target future architecture

```text
                    ┌──────────────────────────┐
                    │          ANIE             │
                    │                            │
                    │ Model / Reasoning / Context │
                    │ Network Intelligence        │
                    │ Policy / Security           │
                    │                            │
                    │ MCP HOST                    │
                    │    └── MCP CLIENT           │
                    └────────────┬───────────────┘
                                 │
                            MCP Protocol
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
          MCP-MikroTik      MCP-Linux       MCP-Network
             SERVER            SERVER           SERVER
                │                │                │
                ▼                ▼                ▼
            RouterOS           Linux          Network
```

ANIE is the intelligence application and MCP Host. It is not where
vendor/network-specific execution logic lives — that belongs to
independent MCP servers, each its own project, speaking the real MCP
protocol to ANIE's (future) MCP Client. **That MCP Client, and the actual
standards-compliant protocol, are not yet implemented** — this phase only
clears the vendor-specific code out of the way and leaves a client-side
skeleton (transport/protocol/errors framing) in place to build on.

This repository does **not** implement DIO/APCE, an inventory system, a
credential vault, a general read/write/execute framework, a scheduler,
automation, voice, a GUI, persistent memory, RAG, autonomous remediation,
multi-agent orchestration, or production deployment.

---

## What changed in this phase

- **Removed from ANIE's active source tree** (moved to
  `archive/phase2-mcp-network-extraction/`, not deleted from history):
  - `app/adapters/mikrotik.py`, `app/mcp/servers/mikrotik_server.py`,
    `tests/test_mikrotik_adapter.py` — MikroTik/RouterOS.
  - `app/adapters/generic.py`, `app/mcp/servers/generic_server.py`,
    `tests/test_generic_adapter.py` — generic ping/traceroute/DNS/TCP.
  - `app/adapters/linux.py`, `tests/test_linux_adapter.py` — Linux
    placeholder.
  - `app/capabilities/` (all of it: `types.py`, `registry.py`,
    `validation.py`, `definitions.py`, `executor.py`), `app/adapters/base.py`,
    `app/mcp/server.py`, `app/mcp/adapter_handler.py`, `app/mcp/bootstrap.py`,
    and their tests (`test_capability_registry.py`,
    `test_capability_validation.py`, `test_capability_executor.py`,
    `test_adapter_handler.py`, `test_mcp_server.py`, `test_agent_tools.py`)
    — the custom protocol's server-side scaffolding and the
    registry/executor that hardcoded vendor capability schemas.
- **Kept in ANIE, unchanged**: `app/core/` (Agent, config, types, logging),
  `app/models/` (router + Ollama/NVIDIA providers), `app/events/`, `cli/`.
- **Kept in ANIE, as a generic (no longer vendor-coupled) MCP Client
  skeleton**: `app/mcp/transport.py`, `app/mcp/protocol.py`,
  `app/mcp/client.py`, `app/mcp/errors.py`, and `tests/test_mcp_client.py`.
  These were judged generic enough to remain — `MCPClient` doesn't know or
  care what's on the other end of a `Transport`. They still speak the
  original **custom** protocol (`discover`/`invoke`/`ping`), which is
  explicitly *not* claimed to be standards-compliant MCP.
- **`app/core/agent.py`**: the bounded tool-calling loop
  (`_run_tool_loop`) is unchanged in behavior, but is now typed against a
  small local `ToolExecutor` protocol instead of importing the
  now-extracted `CapabilityExecutor`. Passing no `tool_executor` (the
  default) behaves exactly as before.
- **`cli/main.py`**: no longer imports or wires up the extracted capability
  registry/executor. `build_agent()` always builds an `Agent` with
  `tool_executor=None` — ANIE currently runs with no tools available to
  the model, the same as Phase 0/1, regardless of `config.yaml`'s
  `mcp.servers` section.
- **`config/config.yaml`**: `mcp.servers` now defaults to an explicit empty
  list (`mcp: servers: []`) rather than a commented-out example that named
  now-nonexistent modules (`app.mcp.servers.mikrotik_server` /
  `app.mcp.servers.generic_server`). A generic, clearly-a-placeholder
  example is included in a comment instead.
- **`.env.example`**: the MikroTik credential section now explains those
  variables belong to the future standalone MCP-MikroTik project, not to
  ANIE.

---

## Installation

No dependency changes from before — `requests` remains a dependency of the
kept `ModelProvider`s (Ollama/NVIDIA); nothing MikroTik/network-adapter
specific pulls it in anymore, but it's still needed either way.

```bash
cd anie
./setup.sh          # or setup.ps1 on Windows
# or: pip install -e ".[dev]"
```

---

## Configuration

```yaml
mcp:
  servers: []
```

- `mcp.servers` parsing (`app/core/config.py`) is unchanged and still
  validates `name`/`command`/`transport`/`timeout_seconds` — but nothing in
  ANIE currently connects to whatever is configured there, since the
  `CapabilityExecutor` that used to consume it was extracted. Leave it
  empty until a new MCP Client-backed tool executor exists.
- Do not point this at the archived `mikrotik_server.py`/
  `generic_server.py` — they no longer exist at those module paths inside
  ANIE, and running them from the archive directly would require fixing
  their `app.*` imports first (see the archive's `MANIFEST.md`).

---

## Capabilities

None are currently wired into the Agent's tool loop. The capability
definitions that used to describe `mikrotik_get_*`, `linux_get_*`,
`ping`/`traceroute`/`dns_lookup`/`tcp_connectivity` now live in
`archive/phase2-mcp-network-extraction/capability-layer/capabilities/definitions.py`
as reference material.

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```

ANIE's test suite (post-extraction) covers only what remains in ANIE core:

- **Model providers** (`test_ollama_provider.py`, `test_nvidia_provider.py`):
  unchanged — generate/fallback/error-handling/tool-calling-passthrough
  (parsing a provider-native `tool_calls` response into `ToolCall`s is
  still exercised; nothing here depended on the removed capability layer).
- **Model router** (`test_router.py`): unchanged.
- **Agent** (`test_agent.py`): unchanged — fallback orchestration, context
  building, structured error/response handling. Does **not** cover the
  tool-calling loop (see "Known Limitations").
- **Config** (`test_config.py`): unchanged, including `mcp.servers`
  parsing/validation — that config surface still exists even though
  nothing consumes it yet.
- **Event bus** (`test_event_bus.py`): unchanged.
- **CLI** (`test_cli.py`): unchanged.
- **MCP Client** (`test_mcp_client.py`): unchanged — connect/disconnect,
  tool discovery, invocation, every typed error path, all against a fake
  in-memory `Transport`. No vendor server involved.

Everything else (capability registry/validation/executor, adapter/MCP-
server bridge, the MCP request/response server loop, MikroTik/generic/
Linux adapters, and the Agent-tool-loop integration test) moved to
`archive/phase2-mcp-network-extraction/*/tests/` along with the code they
exercised — see the archive's `MANIFEST.md`.

---

## Architecture reference

### Project layout

```text
anie/
├── app/
│   ├── core/
│   │   ├── agent.py            # tool-calling loop, now typed against a
│   │   │                        # local ToolExecutor protocol
│   │   ├── config.py           # mcp.servers section (parsed, unwired)
│   │   ├── logging_setup.py
│   │   └── types.py            # ToolCall, Context.tools, ExecutionResult.tool_calls
│   ├── models/
│   │   ├── base.py
│   │   ├── router.py
│   │   └── providers/
│   │       ├── nvidia.py
│   │       └── ollama.py
│   ├── mcp/                     # generic MCP Client skeleton only
│   │   ├── protocol.py           # MCPRequest/MCPResponse/ToolSchema (custom protocol)
│   │   ├── transport.py          # Transport interface + StdioTransport
│   │   ├── client.py             # MCPClient
│   │   └── errors.py             # MCPError and subclasses
│   └── events/
│       └── bus.py
├── cli/
│   └── main.py                  # Agent always built with tool_executor=None
├── config/
│   └── config.yaml              # mcp.servers: [] by default
├── tests/                       # ANIE-core tests only
├── archive/
│   └── phase2-mcp-network-extraction/   # extracted vendor/protocol code
│       ├── MANIFEST.md
│       ├── mikrotik/
│       ├── generic-network/
│       ├── linux/
│       ├── capability-layer/
│       ├── configs/
│       └── documentation/
├── .env.example
└── README.md
```

### Core contracts (unchanged)

- **`Transport`** (`app/mcp/transport.py`): a bidirectional,
  message-oriented channel (`connect`/`disconnect`/`send`/`receive`). Only
  `StdioTransport` (subprocess) is implemented; `MCPClient` depends only on
  this interface.
- **`MCPClient`** (`app/mcp/client.py`): `connect()`, `disconnect()`,
  `discover_tools()` (cached), `invoke_tool()`. Raises `MCPConnectionError`,
  `MCPTimeoutError`, `MCPMalformedResponseError`, `MCPDisconnectedError`, or
  `MCPNotConnectedError` for expected failure modes.
- **`Context.tools`** / **`ExecutionResult.tool_calls`**
  (`app/core/types.py`): the minimal tool-calling contract on `Context`/
  `ExecutionResult` — unchanged, provider-agnostic, no breaking change to
  `ModelProvider.generate()`.
- **`Agent`** (`app/core/agent.py`): unchanged fallback logic
  (`_generate_with_fallback`) and unchanged bounded tool loop
  (`_run_tool_loop`, default 3 iterations), now typed against a local
  `ToolExecutor` protocol (`execute()` + `get_tool_definitions()`) instead
  of the extracted `CapabilityExecutor`. With no `tool_executor` configured
  (the current default via `cli/main.py`), behavior is identical to
  Phase 0/1.

### Important protocol caveat

The `discover`/`invoke`/`ping` newline-delimited-JSON protocol spoken by
`app/mcp/protocol.py`/`client.py` (and, in the archive, `server.py`) is a
**custom prototype**, not the official Model Context Protocol. It is kept
as a working, tested client-side skeleton to build on, not represented as
standards-compliant. A future phase implementing real MCP Host/Client
behavior will likely need to replace this protocol layer, not just extend
it.

---

## Remaining / Out of Scope

Per the original brief, still not implemented (deferred to later phases):
DIO, APCE, an inventory system, a credential vault, a general
read/write/execute framework, a scheduler, event-driven automation, voice/
STT/TTS, a GUI/PWA, persistent memory, RAG, advanced autonomous network
reasoning/remediation, multi-agent orchestration, and production
deployment (Docker/systemd/etc.).

Specific to this extraction phase:

- **The final MCP-MikroTik server was explicitly not built here.** The
  archived MikroTik adapter (`archive/.../mikrotik/adapters/mikrotik.py`)
  is a working, tested reference implementation for that future project,
  not a deliverable of this phase.
- **No real MCP Client (standards-compliant) exists yet.** `app/mcp/`
  is a skeleton in the right shape (transport abstraction, typed errors,
  connect/discover/invoke), speaking the old custom protocol, ready to be
  extended or replaced once real MCP is implemented.
- **`Agent`'s tool-calling loop has no test coverage in ANIE's own suite
  right now.** It exercised the extracted `CapabilityExecutor`
  end-to-end via `test_agent_tools.py`, which moved to the archive along
  with that class. The loop's code is unchanged and still present in
  `app/core/agent.py`; a new tool executor implementation (and matching
  tests) is needed before this is covered again.
- **`config.mcp.servers` is parsed but not consumed.** Nothing in ANIE
  currently builds an `MCPClient` from it — that wiring lived in the
  now-extracted `app/mcp/bootstrap.py`.
