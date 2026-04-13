# FlowGate

**Local-first, OpenAI-compatible LLM gateway for teams who want one endpoint, one dashboard, and full control over routing, credentials, and observability.**

FlowGate sits between your applications and model providers. Your apps talk to a single OpenAI-style base URL, while FlowGate handles provider credentials, optional smart routing, request logging, model discovery, and a built-in dashboard.

It is designed for developers who want a practical self-hosted control plane without sending prompts, logs, or routing decisions to a third-party gateway.

## Why FlowGate

- **OpenAI-compatible by default**: point existing SDKs to `http://host:7798/v1` and keep most client code unchanged.
- **Local-first observability**: request logs, token usage, latency, and routing metadata stay in local SQLite.
- **Encrypted provider vault**: provider API keys are stored encrypted at rest and unlocked only when needed.
- **Multi-provider routing**: route across OpenAI, Anthropic, Gemini, DeepSeek, Qwen, Groq, custom OpenAI-compatible endpoints, and more.
- **Operator-friendly dashboard**: manage providers, models, caller tokens, logs, analytics, router settings, and integration snippets from one UI.
- **Optional smart router**: use fast rule-based complexity scoring or RouteLLM-powered classifier routing.

## What It Ships

| Area | What FlowGate provides |
| --- | --- |
| **Proxy** | `POST /v1/chat/completions`, streaming chat completions, `POST /v1/embeddings`, and `GET /v1/models`. |
| **Dashboard** | Analytics, request logs, provider management, model catalog, router configuration, caller token management, and integration help. |
| **Security** | Encrypted provider key storage, master-password unlock flow, caller token access control, IP allowlisting, and log redaction. |
| **Routing** | Pass-through mode, rule-based complexity routing, and optional RouteLLM classifier routing with graceful fallback. |
| **Catalog** | Sync model lists from provider `/models` endpoints and reuse them in the UI and router configuration. |
| **Packaging** | Python package, FastAPI app, Typer CLI, and a statically exported Next.js dashboard served by the API process. |

## Architecture

```text
Your App / Agent / SDK
        |
        | OpenAI-compatible requests
        v
  FlowGate Proxy  ------------------------------+
        |                                       |
        | auth + routing + logging              |
        v                                       |
  LiteLLM forwarding layer                      |
        |                                       |
        +--> Provider vault (encrypted keys)    |
        +--> Smart router service               |
        +--> SQLite logs + model catalog        |
        +--> Static dashboard UI                |
        |
        v
OpenAI / Anthropic / Gemini / DeepSeek / Qwen / custom OpenAI-compatible backends
```

## Key Capabilities

### 1. Drop-in OpenAI compatibility

FlowGate exposes an OpenAI-style API surface so existing clients can usually switch by changing only the base URL and token source.

Supported endpoints today:

- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `GET /v1/models`

Streaming chat completions are forwarded as SSE.

### 2. Local observability that is actually usable

Every proxied request can be logged with:

- requested model and routed model
- provider
- prompt, response, and error status
- token usage
- latency
- smart-router score and tier
- session metadata

The dashboard surfaces this through overview metrics, timelines, provider/model breakdowns, and per-request log detail views.

### 3. Built-in security controls

FlowGate separates **caller access** from **provider credentials**:

- **Caller tokens** control who is allowed to use the proxy.
- **Provider keys** are stored encrypted in SQLite.
- **Master-password unlock** protects the provider vault.
- **IP allowlisting** limits where requests may come from.
- **Log redaction** helps prevent accidental credential leakage in persisted logs.

If no caller tokens exist yet, proxy access remains open for easier local setup. Once tokens are created, valid caller tokens become mandatory.

### 4. Smart routing without leaving the box

FlowGate supports three routing modes:

- **`off`**: pass through the requested model unchanged
- **`complexity`**: local rule-based routing using a 7-dimension prompt complexity scorer
- **`classifier`**: RouteLLM-based routing, mapped back into FlowGate's four-tier model layout

Both routing strategies use the same tier mapping:

- `SIMPLE`
- `MEDIUM`
- `COMPLEX`
- `REASONING`

If RouteLLM is unavailable or fails at runtime, FlowGate falls back to rule-based routing instead of breaking requests.

## Install

### Base install

```bash
pip install flow-llm-router
```

### Optional extras

```bash
# RouteLLM-based classifier routing
pip install 'flow-llm-router[classifier]'

# ChromaDB-backed skills support
pip install 'flow-llm-router[skills]'
```

## Quick Start

### 1. Start FlowGate

```bash
flow-router start
```

Default endpoints:

- Dashboard: `http://127.0.0.1:7798`
- Proxy base URL: `http://127.0.0.1:7798/v1`
- OpenAPI docs: `http://127.0.0.1:7798/docs`

To load a custom config file:

```bash
export FLOWGATE_CONFIG=/path/to/flowgate.yaml
flow-router start
```

### 2. Open the dashboard

Go to [http://127.0.0.1:7798](http://127.0.0.1:7798) and:

- set up or unlock the vault
- add one or more provider keys
- optionally sync provider models
- optionally create caller tokens
- optionally configure the smart router

### 3. Point your SDK at FlowGate

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:7798/v1",
    api_key="fgt_your_caller_token_or_dummy",
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello from FlowGate"}],
)

print(response.choices[0].message.content)
```

If you have not created any caller tokens yet, FlowGate accepts requests without token enforcement. In production, create caller tokens and restrict access explicitly.

## Configuration

Copy the example file and adjust it for your environment:

```bash
cp flowgate.yaml.example flowgate.yaml
```

Main configuration areas:

- `server`: bind host and port
- `smart_router`: routing strategy and tier mappings
- `skills`: optional retrieval support
- `database`: SQLite database path
- `logging`: prompt/response logging and secret redaction
- `security`: vault, auth token TTL, persisted master key path, and IP allowlisting

Example smart-router configuration:

```yaml
smart_router:
  enabled: true
  strategy: complexity   # complexity | classifier | off
  tiers:
    SIMPLE: gpt-4o-mini
    MEDIUM: gpt-4o
    COMPLEX: claude-sonnet
    REASONING: o1-preview
```

Environment references such as `${OPENAI_API_KEY}` are supported in YAML values.

## CLI

| Command | Purpose |
| --- | --- |
| `flow-router start` | Start the FastAPI server and static dashboard |
| `flow-router add-key` | Interactively add a provider key to the encrypted vault |
| `flow-router version` | Print the installed FlowGate version |

Use `flow-router --help` for all flags and options.

## Development

```bash
git clone <your-repo-url>
cd flow-llm-router
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,classifier]'
pytest -q
```

Frontend workflow:

```bash
cd frontend
npm ci
npm run build
```

To build the static dashboard and copy it into the package:

```bash
bash scripts/build_frontend.sh
```

## Documentation

| Document | Focus |
| --- | --- |
| [docs/DESIGN.md](docs/DESIGN.md) | Design entry point and guide to the current documentation structure |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System layout, runtime components, request flow, and storage model |
| [docs/API_AND_OPERATIONS.md](docs/API_AND_OPERATIONS.md) | API surface, auth flow, provider onboarding, and operational notes |
| [docs/SMART_ROUTER.md](docs/SMART_ROUTER.md) | Smart-router strategies, config schema, API payloads, and fallback behavior |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local development, frontend build flow, testing, and contribution notes |
| [docs/TESTING.md](docs/TESTING.md) | Backend test coverage, smoke-test entry points, and verification guidance |

## Project Status

FlowGate is currently **alpha** and focused on shipping a tight local gateway experience for AI developers and small teams.

Current strengths:

- OpenAI-compatible local proxying
- encrypted provider credential handling
- integrated analytics and logs
- configurable smart routing
- model catalog sync
- local dashboard operations

Current gaps:

- no formal multi-node deployment story yet
- no official container or Helm distribution in this repository yet
- no guaranteed backward-compatibility promise across early releases

## Roadmap Direction

The current codebase suggests a clear path for the project:

- broaden provider ergonomics for custom OpenAI-compatible gateways
- deepen router evaluation and cost/quality observability
- improve deployment and packaging workflows
- harden authentication and admin-session handling
- expand documentation and operator guidance

## License

MIT
