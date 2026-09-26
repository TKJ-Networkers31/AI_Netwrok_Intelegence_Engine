# ANIE — Phase 0: Architecture & Foundation

ANIE (AI Network Intelligence Engine) is a standalone network engineering AI
system. **Phase 0** implements the foundational architecture and a minimal
working flow: a CLI that sends a prompt through an Agent, a ModelRouter, and
an Ollama model provider, and returns a real response from a local model.

```text
CLI
 │
 ▼
Agent
 │
 ▼
ModelRouter
 │
 ▼
ModelProvider (OllamaProvider)
 │
 ▼
Ollama
 │
 ▼
Local Model
```

This phase intentionally implements **only** the foundation described below.
It does not include MCP, device connections, automation, scheduling, voice,
persistent memory, or any other later-phase capability.

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running locally (or reachable
  over the network)
- A pulled Ollama model (default: `qwen3:1.7b`)

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
`requests`) plus `pytest` and `pytest-asyncio`. Remember to activate the
venv (`.\.venv\Scripts\Activate.ps1` or `source .venv/bin/activate`) in
every new shell before running `anie` or `pytest`.

### Option B — editable install

```bash
cd anie
pip install -e ".[dev]"
```

This registers the `anie` command directly, but requires `setuptools` to be
resolvable by pip (Option A avoids that build-isolation step entirely).

---

## Starting Ollama

```bash
# Install Ollama: https://ollama.com/download
ollama serve            # start the Ollama server (if not already running)
ollama pull qwen3:1.7b  # pull the default model used by config/config.yaml
```

By default Ollama listens on `http://localhost:11434`.

---

## Configuration

Configuration lives in `config/config.yaml`:

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

runtime:
  log_level: INFO
```

Any field under `model.primary` or `runtime` can be overridden with an
environment variable, which is useful for secrets/deployment-specific values
that should not be committed to source control. See `.env.example`:

| Variable                     | Overrides                    |
|-------------------------------|-------------------------------|
| `ANIE_CONFIG_PATH`            | which config file is loaded  |
| `ANIE_MODEL_PROVIDER`         | `model.primary.provider`     |
| `ANIE_MODEL_NAME`             | `model.primary.model`        |
| `ANIE_MODEL_BASE_URL`         | `model.primary.base_url`     |
| `ANIE_MODEL_TIMEOUT_SECONDS`  | `model.primary.timeout_seconds` |
| `ANIE_LOG_LEVEL`              | `runtime.log_level`          |

Configuration is validated on load: a missing/unsupported provider, a
missing model name or base URL, or an invalid timeout all raise a clear
`ConfigError` instead of failing deep inside provider code.

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
include structured error details (e.g. raw provider response) in CLI error
output.

If you installed with `pip install -e .`, the `anie` command is available
directly. Otherwise, run it as a module:

```bash
python -m cli.main "Explain VLAN"
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

The unit test suite requires no running Ollama server — all provider calls
are mocked via `unittest.mock`. Tests cover:

- **Agent**: accepts input, returns a structured `ExecutionResult`, handles
  provider errors.
- **Configuration**: valid config loads; missing file, missing provider,
  unsupported provider, missing model name, invalid timeout, and invalid
  YAML all fail clearly; environment overrides apply.
- **OllamaProvider**: successful generation, timeout, connection error,
  model-not-found (404), server error (5xx), empty response content,
  `health_check()` true/false paths.
- **ModelRouter**: selects the configured provider; rejects an unsupported
  provider.
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
│   │   ├── agent.py           # Agent: input -> Context -> Router -> ExecutionResult
│   │   ├── config.py          # Typed config loading (YAML + env overrides)
│   │   ├── logging_setup.py   # Structured logging configuration
│   │   └── types.py           # Context, Message, ExecutionResult, ErrorCode
│   ├── models/
│   │   ├── base.py            # ModelProvider abstract interface
│   │   ├── router.py          # ModelRouter: resolves the configured provider
│   │   └── providers/
│   │       └── ollama.py      # OllamaProvider implementation
│   └── events/
│       └── bus.py             # Minimal async-safe EventBus
├── cli/
│   └── main.py                # CLI entrypoint (single-shot + interactive)
├── config/
│   └── config.yaml            # Default configuration
├── tests/                     # pytest suite (mocked providers, no live Ollama needed)
├── .env.example
├── .gitignore
├── requirements.txt            # runtime deps (pyyaml, requests)
├── requirements-dev.txt        # + pytest, pytest-asyncio
├── setup.ps1                   # Windows venv + install
├── setup.sh                    # macOS/Linux venv + install
├── pyproject.toml
└── README.md
```

### Core contracts

- **`ModelProvider`** (`app/models/base.py`): abstract interface with
  `generate(context) -> ExecutionResult` and `health_check() -> bool`. New
  providers (future phases) implement this interface without touching
  `Agent` or `ModelRouter` call sites.
- **`ModelRouter`** (`app/models/router.py`): resolves the single configured
  primary provider at construction time. Phase 0 has no fallback, load
  balancing, or capability matching — that abstraction is deliberately left
  for later phases.
- **`Context`** (`app/core/types.py`): minimal structured conversation
  state (`system_prompt` + `messages`). No persistence — a `Context` exists
  only for the lifetime of one `agent.run(...)` call.
- **`ExecutionResult`** (`app/core/types.py`): structured result with
  `success`, `response`, `error` (a structured `ExecutionError` with a
  stable `ErrorCode`), and `metadata`, used everywhere instead of raw
  dicts/exceptions crossing module boundaries.
- **`Agent`** (`app/core/agent.py`): the single entry point. Builds a
  `Context`, asks the `ModelRouter` for the active provider, calls
  `generate()`, publishes `agent.request` / `agent.response` / `agent.error`
  events, and returns an `ExecutionResult`. It has no provider-specific
  knowledge.
- **`EventBus`** (`app/events/bus.py`): minimal publish/subscribe bus
  supporting both sync and async handlers. No automation/event rules yet.

### Error handling

All expected failure modes are represented as `ErrorCode` values rather than
raw exceptions crossing the Agent/CLI boundary:

- `invalid_configuration`
- `invalid_provider`
- `provider_unavailable` (connection refused, 5xx from Ollama)
- `connection_timeout`
- `model_unavailable` (model not pulled / 404 from Ollama)
- `model_request_failed` (malformed response, 4xx, etc.)

The CLI prints a concise `Error [<code>]: <message>` line by default; pass
`--debug` to also print structured `details` (e.g. the raw provider
response) that are otherwise only sent to the log stream.

### Logging

Structured logging (`app/core/logging_setup.py`) configures the `anie`
logger hierarchy with a consistent field set: `timestamp`, `level`,
`component`, `event`, `request_id`, `message`. Key events logged:
`agent.request`, `model.request`, `model.response`, `model.error`. No
secrets are ever logged.
