# ANIE — Phase 1: Model Intelligence & Provider Fallback

ANIE (AI Network Intelligence Engine) is a standalone network engineering AI
system.

**Phase 0** implemented the foundational architecture: a CLI that sends a
prompt through an Agent, a ModelRouter, and a single Ollama model provider.

**Phase 1** (this phase) extends the model layer with automatic fallback:

```text
CLI
 │
 ▼
Agent
 │
 ▼
ModelRouter
 ├── Ollama (primary)
 └── NVIDIA (fallback)
 │
 ▼
Local Model / NVIDIA-hosted Model
```

When the primary provider (Ollama) fails with a recoverable runtime error
(connection refused, timeout, model not pulled, malformed response, etc.),
the Agent automatically retries the same request against the fallback
provider (NVIDIA) before giving up. If both fail, ANIE returns a single
structured, readable error describing both failures.

This phase does **not** include MCP, device connections, automation,
scheduling, voice, persistent memory, or any other later-phase capability.

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running locally (or reachable
  over the network) for the primary provider
- A pulled Ollama model (default: `qwen3:1.7b`)
- *(Optional)* An [NVIDIA API key](https://build.nvidia.com/) if you want to
  enable the NVIDIA fallback provider

---

## Installation

### Option A — virtual environment + requirements files (recommended)

**Windows (PowerShell):**
```powershell
cd anie
.\setup.ps1
```
or manually:
```powershell
cd anie
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

**macOS / Linux:**
```bash
cd anie
./setup.sh
```
or manually:
```bash
cd anie
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in `requirements.txt` (runtime deps: `pyyaml`,
`requests`) plus `pytest` and `pytest-asyncio`. Phase 1 adds no new runtime
dependencies — the NVIDIA provider reuses `requests`, same as Ollama.
Remember to activate the venv in every new shell before running `anie` or
`pytest`.

### Option B — editable install

```bash
cd anie
pip install -e ".[dev]"
```

---

## Starting Ollama (primary provider)

```bash
# Install Ollama: https://ollama.com/download
ollama serve            # start the Ollama server (if not already running)
ollama pull qwen3:1.7b  # pull the default model used by config/config.yaml
```

By default Ollama listens on `http://localhost:11434`.

---

## Configuration

Configuration lives in `config/config.yaml`. The `model.primary` section is
required (same as Phase 0); `model.fallback` is new in Phase 1 and
**optional** — omit it entirely and ANIE behaves exactly like Phase 0.

```yaml
app:
  name: ANIE
  environment: development

model:
  primary:
    provider: ollama
    model: qwen3:1.7b
    base_url: http://localhost:11434
    timeout_seconds: 60

  # Optional. Enables automatic fallback to NVIDIA when the primary
  # provider fails with a recoverable runtime error.
  fallback:
    provider: nvidia
    model: meta/llama-3.1-8b-instruct
    base_url: https://integrate.api.nvidia.com/v1   # defaults to this if omitted
    api_key_env: NVIDIA_API_KEY                       # defaults to this if omitted
    timeout_seconds: 30

  # Optional shared default. Used for any of the sections above that don't
  # set their own timeout_seconds.
  timeout: 30

runtime:
  log_level: INFO
```

**NVIDIA credentials are never stored in `config.yaml`.** `api_key_env`
names an environment variable (default `NVIDIA_API_KEY`); the actual key
value is read from the environment at request time, only by
`NvidiaProvider`, and is never logged, never placed in an error message or
error `details`, and never appears anywhere in the parsed `Config` object.

### Environment variable overrides

Any field can be overridden with an environment variable, which is useful
for secrets/deployment-specific values that should not be committed to
source control. See `.env.example`:

| Variable                        | Overrides                       |
|----------------------------------|----------------------------------|
| `ANIE_CONFIG_PATH`               | which config file is loaded     |
| `ANIE_MODEL_PROVIDER`            | `model.primary.provider`        |
| `ANIE_MODEL_NAME`                | `model.primary.model`           |
| `ANIE_MODEL_BASE_URL`            | `model.primary.base_url`        |
| `ANIE_MODEL_TIMEOUT_SECONDS`     | `model.primary.timeout_seconds` |
| `ANIE_FALLBACK_PROVIDER`         | `model.fallback.provider`       |
| `ANIE_FALLBACK_MODEL`            | `model.fallback.model`          |
| `ANIE_FALLBACK_BASE_URL`         | `model.fallback.base_url`       |
| `ANIE_FALLBACK_TIMEOUT_SECONDS`  | `model.fallback.timeout_seconds`|
| `ANIE_FALLBACK_API_KEY_ENV`      | `model.fallback.api_key_env`    |
| `ANIE_MODEL_TIMEOUT`             | shared `model.timeout` default  |
| `ANIE_LOG_LEVEL`                 | `runtime.log_level`             |
| `NVIDIA_API_KEY`                 | the NVIDIA API key itself (read directly by `NvidiaProvider`, not by `Config`) |

Setting any `ANIE_FALLBACK_*` variable is enough to enable a fallback
provider even when `config.yaml` has no `model.fallback` section at all.

Configuration is validated on load: a missing/unsupported provider (in
either `primary` or `fallback`), a missing model name or base URL, or an
invalid timeout all raise a clear `ConfigError` instead of failing deep
inside provider code.

---

## Running ANIE

Single-shot:

```bash
anie "Explain VLAN"
```

Interactive mode:

```bash
anie
ANIE > Explain VLAN
ANIE > What is trunking?
ANIE > exit
```

Use `--config <path>` to point at a different config file, and `--debug` to
include structured error details (e.g. raw provider response, or both
providers' errors on a full fallback failure) in CLI error output.

If you installed with `pip install -e .`, the `anie` command is available
directly. Otherwise, run it as a module:

```bash
python -m cli.main "Explain VLAN"
```

### Fallback behavior at a glance

```text
Ollama available          → response comes from Ollama, no fallback attempted
Ollama unavailable/times   → ANIE automatically retries via NVIDIA
  out/model missing/etc.     (only if model.fallback is configured)
    NVIDIA succeeds         → response comes from NVIDIA
    NVIDIA also fails       → structured error naming BOTH failures
                              (ErrorCode: all_providers_failed)
```

Fallback is only attempted for runtime/provider failures returned by
`generate()` (connection errors, timeouts, missing model, authentication
failure, malformed response). It is never attempted for configuration
problems — those are validated once at startup (`Config.load` /
`ModelRouter.__init__`) and simply prevent ANIE from starting at all.

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```

The unit test suite requires no running Ollama server and no NVIDIA API
key/internet access — all provider calls are mocked via `unittest.mock`.
Tests cover:

- **Agent**: accepts input, returns a structured `ExecutionResult`, handles
  provider errors, and (Phase 1) automatically falls back to a configured
  fallback provider on primary failure, does *not* call the fallback when
  the primary succeeds, reports a structured `all_providers_failed` error
  when both fail, and behaves exactly like Phase 0 against a router with no
  fallback support at all.
- **Configuration**: valid config loads (with and without a `fallback`
  section); missing file, missing provider, unsupported provider (primary
  or fallback), missing model name, invalid timeout, and invalid YAML all
  fail clearly; primary/fallback/shared-timeout environment overrides
  apply; the NVIDIA API key value is never present anywhere in a parsed
  `Config`.
- **OllamaProvider**: successful generation, timeout, connection error,
  model-not-found (404), server error (5xx), empty response content,
  `health_check()` true/false paths.
- **NvidiaProvider**: successful generation, missing API key (fails without
  making a network call), authentication failure (401/403, key never
  leaked in the error), timeout, connection error, model-not-found (404),
  server error (5xx), malformed response, `health_check()` true/false
  paths.
- **ModelRouter**: selects the configured primary provider; resolves an
  optional NVIDIA fallback provider; rejects an unsupported provider in
  either section; reports whether a fallback is configured.
- **EventBus**: publish/subscribe with sync and async handlers,
  unsubscribe, `publish_sync`.
- **CLI**: single-shot success/error output formatting.

---

## Architecture

### Project layout

```text
anie/
├── app/
│   ├── core/
│   │   ├── agent.py           # Agent: input -> Context -> Router -> Provider (+ fallback) -> ExecutionResult
│   │   ├── config.py          # Typed config loading (YAML + env overrides, primary + fallback)
│   │   ├── logging_setup.py   # Structured logging configuration
│   │   └── types.py           # Context, Message, ExecutionResult, ErrorCode
│   ├── models/
│   │   ├── base.py            # ModelProvider abstract interface (+ capabilities())
│   │   ├── router.py          # ModelRouter: resolves primary + optional fallback provider
│   │   └── providers/
│   │       ├── ollama.py      # OllamaProvider implementation
│   │       └── nvidia.py      # NvidiaProvider implementation (Phase 1)
│   └── events/
│       └── bus.py             # Minimal async-safe EventBus
├── cli/
│   └── main.py                # CLI entrypoint (single-shot + interactive)
├── config/
│   └── config.yaml            # Default configuration (fallback section commented out)
├── tests/                     # pytest suite (mocked providers, no live Ollama/NVIDIA needed)
├── .env.example
├── .gitignore
├── requirements.txt            # runtime deps (pyyaml, requests) — unchanged in Phase 1
├── requirements-dev.txt        # + pytest, pytest-asyncio
├── setup.ps1                   # Windows venv + install
├── setup.sh                    # macOS/Linux venv + install
├── pyproject.toml
└── README.md
```

### Core contracts

- **`ModelProvider`** (`app/models/base.py`): abstract interface with
  `generate(context) -> ExecutionResult`, `health_check() -> bool`, and
  (Phase 1) `capabilities() -> dict` — a lightweight, static
  `{text, streaming, tool_calling, vision}` map. There is no capability
  registry or capability-based routing yet; it exists so future phases can
  branch on it without another interface change.
- **`ModelRouter`** (`app/models/router.py`): resolves the configured
  primary provider eagerly at construction time (unchanged from Phase 0),
  and now also resolves an optional fallback provider the same way. Routing
  stays deterministic: `get_provider()` always returns the primary,
  `get_fallback_provider()` returns the fallback or `None`. There is still
  no load balancing or capability matching.
- **`Context`** (`app/core/types.py`): minimal structured conversation
  state (`system_prompt` + `messages`), unchanged and still
  provider-independent — the same `Context` is reused for both the primary
  and fallback `generate()` calls.
- **`ExecutionResult`** (`app/core/types.py`): structured result with
  `success`, `response`, `error` (a structured `ExecutionError` with a
  stable `ErrorCode`), and `metadata`. Phase 1 adds `authentication_failed`
  and `all_providers_failed` error codes, and a successful fallback result
  carries `metadata["used_fallback"] = True` plus
  `metadata["primary_error_code"]` so callers/logs can tell a fallback
  happened.
- **`Agent`** (`app/core/agent.py`): still the single entry point. Builds a
  `Context`, calls the primary provider via the router, and — new in
  Phase 1 — if that call fails with anything other than a configuration
  error, and a fallback provider is configured, retries the same `Context`
  against the fallback before returning. Publishes `agent.request` /
  `agent.fallback` / `agent.response` / `agent.error` events. Uses
  `getattr(router, "get_fallback_provider", None)` defensively, so any
  Phase-0-shaped router (real or test double) that has no concept of
  fallback continues to behave exactly as it did in Phase 0.
- **`NvidiaProvider`** (`app/models/providers/nvidia.py`): talks to an
  OpenAI-compatible `/chat/completions` endpoint (NVIDIA NIM /
  `integrate.api.nvidia.com`). Reads its API key fresh from the environment
  variable named by `api_key_env` on every request (never cached at
  construction, never logged, never placed in error details). Missing key →
  `authentication_failed` without making a network call; 401/403 →
  `authentication_failed`; 404 → `model_unavailable`; 5xx →
  `provider_unavailable`; timeout → `connection_timeout`; malformed/empty
  response → `model_request_failed`.
- **`EventBus`** (`app/events/bus.py`): unchanged from Phase 0.

### Error handling

All expected failure modes are represented as `ErrorCode` values rather than
raw exceptions crossing the Agent/CLI boundary:

- `invalid_configuration`
- `invalid_provider`
- `provider_unavailable` (connection refused, 5xx from Ollama/NVIDIA)
- `connection_timeout`
- `model_unavailable` (model not pulled / 404)
- `model_request_failed` (malformed response, 4xx, etc.)
- `authentication_failed` *(Phase 1)* — missing/invalid NVIDIA API key
- `all_providers_failed` *(Phase 1)* — both primary and fallback failed;
  `details` contains both providers' `{code, message}` so nothing is lost

The CLI prints a concise `Error [<code>]: <message>` line by default; pass
`--debug` to also print structured `details` (e.g. the raw provider
response, or both failures' details on `all_providers_failed`) that are
otherwise only sent to the log stream.

### Logging

Structured logging (`app/core/logging_setup.py`) configures the `anie`
logger hierarchy with a consistent field set: `timestamp`, `level`,
`component`, `event`, `request_id`, `message`. Key events logged:
`agent.request`, `agent.fallback` *(Phase 1)*, `model.request`,
`model.response`, `model.error`, `agent.error`. No secrets — including the
NVIDIA API key — are ever logged.

---

## Remaining / Out of Scope

Per the Phase 1 brief, the following are intentionally **not** implemented
in this phase (deferred to later phases): MCP, MikroTik/Linux/SSH tooling,
credentials manager, scheduler, event-driven automation, voice/STT/TTS,
GUI/PWA, persistent memory, RAG, a network knowledge engine, multi-agent
orchestration, Docker/systemd/production deployment.

Additionally, **streaming generation was intentionally left out of Phase
1.** The task explicitly allowed skipping it if it would meaningfully
complicate the current implementation, and adding it cleanly would require
changing the `ModelProvider.generate() -> ExecutionResult` contract (a
single, complete result) to something that can yield incremental chunks
across both `OllamaProvider` and `NvidiaProvider`, plus a corresponding
change to how the CLI prints a response and how the Agent/EventBus report
partial progress. That is a real interface change, not a provider-local
addition, so it's flagged here as remaining work rather than bolted on.
