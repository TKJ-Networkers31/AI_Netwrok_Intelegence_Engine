# Extraction Manifest — Phase 2 MCP/Network Implementation

## Metadata

```
Original repository:      ANIE (AI Network Intelligence Engine)
Original commit/state:    Reconstructed Phase 2 state (pre-extraction), as
                           provided at the start of this extraction task.
                           NOTE: this working copy was reconstructed file-
                           for-file from the Phase 2 source provided to
                           this task; it was not cloned from a live Git
                           remote. See "Working-environment caveat" below.
Extraction date:          2026-09-27
Purpose:                  Separate the custom MCP-like tool protocol and
                           all vendor-/network-specific execution logic
                           (MikroTik/RouterOS, generic ping/traceroute/DNS/
                           TCP diagnostics, the Linux placeholder, and the
                           capability registry/executor bridging them to
                           that protocol) out of ANIE core, ahead of ANIE
                           becoming a real MCP Host + MCP Client and those
                           vendor implementations becoming independent
                           MCP-MikroTik / MCP-Network server projects.
```

### Working-environment caveat

This extraction was performed in a sandboxed task environment with no
access to the actual ANIE Git remote/working tree — only the Phase 2
source files themselves (as text) were available. To perform a safe,
verifiable extraction (rather than describing one), this sandbox
reconstructed the Phase 2 file tree byte-for-byte from that source,
initialized a local Git repository, committed that reconstruction as a
baseline (`Baseline: reconstructed pre-extraction Phase 2 state ...`),
and then performed the moves described in this manifest as normal commits
on top of it — inspectable via `git log`/`git diff` in this sandbox. **The
person running this task is responsible for applying the same file moves
(or importing this archive) into their actual ANIE repository**; nothing
here touches their real Git history, and no commit/push/reset was ever
run against it.

---

## MikroTik files (`mikrotik/`)

| Original path | Archive path | Purpose | Dependency notes |
|---|---|---|---|
| `app/adapters/mikrotik.py` | `mikrotik/adapters/mikrotik.py` | RouterOS REST API adapter (`MikroTikAdapter`): talks to a RouterOS v7+ device's REST API over HTTPS via `requests`, one fixed read-only endpoint per capability (`interface`, `ip/route`, `ip/arp`, `system/resource`, `log`, `ip/dns`, `ip/dhcp-server/lease`, `ip/firewall/filter`, `ip/address`). Credentials read from env vars at request time, never from config. | Imports `app.adapters.base.Adapter` (now at `capability-layer/adapters/base.py`). Depends on `requests`. |
| `app/mcp/servers/mikrotik_server.py` | `mikrotik/mcp_servers/mikrotik_server.py` | Runnable subprocess entrypoint: builds a `MikroTikAdapter` from CLI args, wraps it in `AdapterToolHandler`, and serves it over `MCPServer` (stdio). | Imports `MikroTikAdapter`, `app.capabilities.definitions.build_default_registry` (now at `capability-layer/capabilities/definitions.py`), `app.mcp.adapter_handler.AdapterToolHandler` and `app.mcp.server.MCPServer` (now at `capability-layer/mcp/`). |
| `tests/test_mikrotik_adapter.py` | `mikrotik/tests/test_mikrotik_adapter.py` | Full adapter test suite: capability listing, missing-credentials (no network call), success, auth failure, timeout, connection error, 404, 5xx, malformed JSON, health check. All HTTP calls mocked — no live RouterOS device required. | pytest + `unittest.mock`. |

**Future destination:** standalone `MCP-MikroTik` server project (its own
repo), exposing these same capabilities through the real MCP protocol
rather than the custom one.

---

## Generic network files (`generic-network/`)

| Original path | Archive path | Purpose | Dependency notes |
|---|---|---|---|
| `app/adapters/generic.py` | `generic-network/adapters/generic.py` | Host-agnostic `ping`/`traceroute`/`dns_lookup`/`tcp_connectivity` adapter. Shells out to the system `ping`/`traceroute` binaries with a fixed, allowlisted argument list (never `shell=True`); DNS/TCP checks use the stdlib `socket` module. | Imports `app.adapters.base.Adapter`. Stdlib only otherwise (`subprocess`, `socket`, `platform`, `re`). |
| `app/mcp/servers/generic_server.py` | `generic-network/mcp_servers/generic_server.py` | Runnable subprocess entrypoint for the generic adapter, same pattern as the MikroTik server. | Same capability-layer dependencies as `mikrotik_server.py`. |
| `tests/test_generic_adapter.py` | `generic-network/tests/test_generic_adapter.py` | Full adapter test suite: host-argument validation/injection-safety, ping/traceroute success/timeout/missing-binary, DNS success/failure, TCP success/refused/timeout, health check. | pytest + `unittest.mock`. |

**Future destination:** candidate building blocks for a standalone
`MCP-Network` server project. Evaluate independently of MikroTik — these
capabilities are host-agnostic diagnostics, not tied to any vendor.

---

## Linux placeholder files (`linux/`)

| Original path | Archive path | Purpose | Dependency notes |
|---|---|---|---|
| `app/adapters/linux.py` | `linux/adapters/linux.py` | Placeholder `LinuxAdapter`: every capability (`linux_get_interfaces`, `_routes`, `_neighbors`, `_processes`, `_cpu`, `_memory`, `_disk`, `_services`, `_logs`, `_dns`) is registered but returns a structured `not_implemented` error — never fabricated data. | Imports `app.adapters.base.Adapter`. No real implementation exists yet. |
| `tests/test_linux_adapter.py` | `linux/tests/test_linux_adapter.py` | Confirms every capability returns `not_implemented` with no fabricated `data` key, unsupported-capability handling, health check. | pytest. |

**Future destination:** either folded into a future `MCP-Network` server
or its own `MCP-Linux` server, once a real implementation (local-host or
SSH-based) is built. Kept separate from `generic-network/` since it was
already namespaced/scoped separately in the original registry.

---

## Capability layer / custom MCP server-side scaffolding (`capability-layer/`)

This is the glue that is NOT itself vendor-specific code, but is tightly
coupled to (a) the custom, non-standard MCP-like protocol
(`discover`/`invoke`/`ping` over newline-delimited JSON) and (b) the
hardcoded vendor capability definitions (`mikrotik_*`/`linux_*` capability
names, schemas, and server-name routing). It was extracted rather than
kept in ANIE core because:

- `app/capabilities/definitions.py` hardcodes MikroTik/Linux capability
  names, descriptions, and schemas directly — this is vendor knowledge
  living in what was meant to be host-agnostic code.
- `app/mcp/server.py` / `app/mcp/adapter_handler.py` are the **server**-side
  half of the custom protocol — used only to build a vendor MCP server
  process (`mikrotik_server.py`, `generic_server.py`). ANIE itself, as an
  MCP Host + Client, has no need to run an MCP *server* — that belongs to
  the separate vendor server projects.
- `app/mcp/bootstrap.py` wires `config.mcp.servers` directly into a
  `CapabilityExecutor`, so it could not stay without the executor/registry
  it constructs.

| Original path | Archive path | Purpose | Dependency notes |
|---|---|---|---|
| `app/capabilities/types.py` | `capability-layer/capabilities/types.py` | `CapabilityDefinition`, `RiskLevel` — the data shapes the registry/executor use. | No internal deps. |
| `app/capabilities/registry.py` | `capability-layer/capabilities/registry.py` | `CapabilityRegistry` — the in-memory allowlist. | Depends on `types.py`. |
| `app/capabilities/validation.py` | `capability-layer/capabilities/validation.py` | Minimal, dependency-free JSON-Schema-*like* argument validation. | No internal deps. |
| `app/capabilities/definitions.py` | `capability-layer/capabilities/definitions.py` | The actual Phase 2 capability set — hardcodes every `mikrotik_*`/`linux_*`/generic capability name, schema, and server routing. **This is the vendor-specific part of this layer.** | Depends on `registry.py`, `types.py`. |
| `app/capabilities/executor.py` | `capability-layer/capabilities/executor.py` | `CapabilityExecutor` — registry lookup -> schema validation -> risk check -> `MCPClient.invoke_tool()` -> normalized `ToolResult`. | Depends on `registry.py`, `types.py`, `validation.py`, and ANIE's *kept* `app.mcp.client`/`app.mcp.errors`. |
| `app/mcp/server.py` | `capability-layer/mcp/server.py` | `MCPServer` — the server-side request/response loop for the custom protocol. | Depends on ANIE's *kept* `app.mcp.protocol`. |
| `app/mcp/adapter_handler.py` | `capability-layer/mcp/adapter_handler.py` | `AdapterToolHandler` — bridges an `Adapter` into the shape `MCPServer` expects. | Depends on `adapters/base.py` (this archive), `capabilities/types.py` (this archive), ANIE's *kept* `app.mcp.protocol`. |
| `app/mcp/bootstrap.py` | `capability-layer/mcp/bootstrap.py` | `build_capability_executor()` — connects every `config.mcp.servers` entry and builds a `CapabilityExecutor`. | Depends on `capabilities/executor.py`, `capabilities/registry.py` (this archive), and ANIE's *kept* `app.mcp.client`/`app.mcp.errors`/`app.mcp.transport`, `app.core.config`. |
| `app/adapters/base.py` | `capability-layer/adapters/base.py` | `Adapter` ABC — the interface every vendor adapter (MikroTik, generic, Linux) implements. | No internal deps. |
| `tests/test_capability_registry.py` | `capability-layer/tests/test_capability_registry.py` | Registry unit tests. | pytest. |
| `tests/test_capability_validation.py` | `capability-layer/tests/test_capability_validation.py` | Validation unit tests. | pytest. |
| `tests/test_capability_executor.py` | `capability-layer/tests/test_capability_executor.py` | Executor unit tests (unknown capability, invalid args, permission denied, server unavailable, success, each MCP error type). | pytest. |
| `tests/test_adapter_handler.py` | `capability-layer/tests/test_adapter_handler.py` | `AdapterToolHandler` bridge tests. | pytest. |
| `tests/test_mcp_server.py` | `capability-layer/tests/test_mcp_server.py` | `MCPServer` protocol-loop tests. | pytest. |
| `tests/test_agent_tools.py` | `capability-layer/tests/test_agent_tools.py` | Agent <-> `CapabilityExecutor` integration tests (tool-call loop, tool error surfaced to model, unregistered tool rejected, iteration cap). **Exercises ANIE's `Agent` against the real (now-extracted) `CapabilityExecutor`** — kept here rather than in ANIE's test suite because it imports the extracted module directly; `Agent`'s tool loop itself is unchanged and remains in ANIE (see "Known limitations"). | pytest. |

**Future destination:** this is the part most likely to be *replaced*
rather than reused verbatim — the long-term design routes
`ANIE -> MCP Client -> MCP Server -> Tool`, not
`ANIE -> CapabilityExecutor -> RouterOS`. It's archived (not deleted)
because the validation/allowlist/risk-check *pattern* it encodes is still
useful reference material for whatever host-side policy layer ANIE
eventually grows on top of a real MCP Client.

---

## Relevant configuration

No dedicated vendor config files existed as separate artifacts — vendor
wiring lived inline in `config/config.yaml`'s commented-out `mcp.servers`
example (pointing at `app.mcp.servers.mikrotik_server` /
`app.mcp.servers.generic_server`) and in `.env.example`'s
`MIKROTIK_USERNAME`/`MIKROTIK_PASSWORD` section. Both were edited in place
in ANIE (not moved) since they're config *examples*, not code — see
`configs/config.yaml.pre-extraction.example` in this archive for the
exact pre-extraction version, preserved for reference.

---

## Known coupling

- Every archived file still uses its **original** `app.*` import paths
  (e.g. `from app.adapters.base import Adapter`,
  `from app.capabilities.registry import CapabilityRegistry`). These paths
  assumed the original ANIE package layout. **Reconstructing a standalone
  MCP-MikroTik/MCP-Network project from this archive will require
  rewriting these imports** to whatever package layout the new project
  uses — they are not directly importable as-is once copied out.
- `capability-layer/capabilities/executor.py` and
  `capability-layer/mcp/bootstrap.py` still depend on `app.mcp.client`,
  `app.mcp.errors`, `app.mcp.transport`, and `app.core.config` — all of
  which **remain in ANIE** (they were judged generic enough to keep; see
  README.md). A standalone project reusing the executor/bootstrap pattern
  will need its own copy of (or a dependency on) an MCP client and
  transport layer.
- `mikrotik_server.py` / `generic_server.py` both depend on
  `capability-layer/capabilities/definitions.py` (for
  `build_default_registry()`) and `capability-layer/mcp/{server,
  adapter_handler}.py` — all three needed together to actually run either
  server process.

## Known missing dependencies

- None of the archived code introduces new third-party dependencies beyond
  what ANIE already used: `requests` (MikroTik adapter) and the Python
  standard library (`subprocess`, `socket`, `json`, etc. — generic adapter,
  MCP server loop).

## Known limitations

- **This is a migration/reference package, not a complete, ready-to-run
  MCP-MikroTik server.** It preserves working, tested implementation code
  and its immediate dependency graph — it does not add MCP-protocol
  compliance, packaging (`pyproject.toml`), a standalone test harness, or
  documentation beyond this manifest. Building the actual standalone
  MCP-MikroTik server is explicitly out of scope for this phase.
- The custom protocol these files speak (`discover`/`invoke`/`ping` over
  newline-delimited JSON) is **not** the official MCP standard. Nothing in
  this archive, or in ANIE's kept `app/mcp/` skeleton, should be presented
  as standards-compliant MCP without further verification against the
  actual specification.
- `test_agent_tools.py` (in `capability-layer/tests/`) is the one test
  that exercised `Agent`'s bounded tool-calling loop end-to-end. With the
  concrete `CapabilityExecutor` it depends on now extracted, **ANIE's own
  test suite no longer has coverage for `Agent._run_tool_loop()`** — the
  loop's code is still present and unchanged in `app/core/agent.py`
  (now typed against a minimal local `ToolExecutor` protocol instead of
  the concrete class), but untested until a new tool executor
  implementation (and matching tests) exists in ANIE. This is called out
  again in the final report's "Known Limitations" section.

## Future destination summary

```
mikrotik/          -> standalone MCP-MikroTik server project
generic-network/    -> candidate MCP-Network server project
linux/              -> candidate MCP-Network or MCP-Linux server project
capability-layer/    -> reference only; the actual future design is
                        ANIE -> MCP Client -> MCP Server -> Tool, not a
                        revival of this custom protocol/executor
```
