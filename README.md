<div align="center">
  <img src="flowapi_logo.png" alt="nanobot" width="500">
  <h1>🚀 Flow-LLM-Router: The Ultimate "Token Saver"</h1>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </p>
</div>


## 📢 Stop Paying the "Token Tax". Cut Your Total LLM Costs by 70%.

To drastically reduce your AI Agent costs, you need to optimize both Token Price and Token Usage. We provide the complete 2-step solution:

🌍 1. The Lowest API Price

💻 2. The Token-Saving Router



## 🔥 Core Features of the flow-llm-router

1. 🧰 Dynamic Skill Loading (Eliminate the "Token Tax")

Stop sending 50 tool definitions in every API call. FlowGate automatically analyzes the user's intent and injects only the top 3 most relevant skills/tools into the prompt.
👉 Impact: Drastically reduces input tokens, saves money, and improves model reasoning by reducing context noise.

1. 🧠 Smart API Routing (Rules & Classifiers)

Don't use a sledgehammer to crack a nut. FlowGate features a built-in routing engine.
Define rules or use our lightweight local classifier to route simple queries to cheaper models (e.g., gpt-4o-mini, llama-3) and complex reasoning tasks to premium models.
👉 Impact: Achieves the perfect balance between high intelligence and low cost.

1. 📊 Automated Token Analytics Dashboard

Built-in beautiful local web dashboard (built with Next.js/TypeScript). Instantly identify your "Token Assassins." Visualize exactly which models, endpoints, or specific prompts are costing you the most.
👉 Impact: Full transparency. What gets measured, gets optimized.

1. 🔒 Secure, Local API Key Management

Your API keys and prompts are yours. FlowGate stores your credentials locally and encrypted. Your app talks to a single OpenAI-style base URL (<http://localhost:8000/v1>), and FlowGate securely handles the downstream provider authentication.
👉 Impact: 100% privacy and no vendor lock-in.

## At A Glance

- [The Problem](#the-problem)
- [Why FlowGate](#why-flowgate)
- [Who It Is For](#who-it-is-for)
- [Use Cases](#use-cases)
- [Why Pair It With FlowAPI](#why-pair-it-with-flowapi)
- [Key Capabilities](#key-capabilities)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [FAQ](#faq)

## Why Flow-LLM-Router

- **OpenAI-compatible by default**: point existing SDKs to `http://host:7798/v1` and keep most client code unchanged.
- **Local-first observability**: request logs, token usage, latency, and routing metadata stay in local SQLite.
- **Encrypted provider vault**: provider API keys are stored encrypted at rest and unlocked only when needed.
- **Multi-provider routing**: route across OpenAI, Anthropic, Gemini, DeepSeek, Qwen, Groq, custom OpenAI-compatible endpoints, and more.
- **Operator-friendly dashboard**: manage providers, models, caller tokens, logs, analytics, router settings, and integration snippets from one UI.
- **Optional smart router**: use fast rule-based complexity scoring or RouteLLM-powered classifier routing.

## Who It Is For

- teams building AI agents, copilots, or workflow automation on top of OpenAI-style SDKs
- developers who want local logs and routing visibility without adopting a hosted observability layer
- operators who need one stable endpoint in front of multiple model providers
- builders who want to combine lower-cost upstream pricing with local request optimization

## Use Cases

- **AI agents and copilots**: centralize routing and provider auth behind one OpenAI-compatible endpoint
- **Multi-model workflows**: send easy tasks to cheap models and reserve premium models for high-value reasoning
- **Private internal tooling**: keep prompts, logs, and credentials inside your own environment
- **Cost debugging**: identify which models, prompts, and traffic patterns are silently increasing your bill
- **Gateway standardization**: give multiple applications one stable base URL even when upstream providers differ

## What It Ships

| Area          | What FlowGate provides                                                                                                            |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Proxy**     | `POST /v1/chat/completions`, streaming chat completions, `POST /v1/embeddings`, and `GET /v1/models`.                             |
| **Dashboard** | Analytics, request logs, provider management, model catalog, router configuration, caller token management, and integration help. |
| **Security**  | Encrypted provider key storage, master-password unlock flow, caller token access control, IP allowlisting, and log redaction.     |
| **Routing**   | Pass-through mode, rule-based complexity routing, and optional RouteLLM classifier routing with graceful fallback.                |
| **Catalog**   | Sync model lists from provider `/models` endpoints and reuse them in the UI and router configuration.                             |
| **Packaging** | Python package, FastAPI app, Typer CLI, and a statically exported Next.js dashboard served by the API process.                    |

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

## Why Not Direct SDK Calls

| Approach                              | What you miss                                                                                                             |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Call OpenAI or Anthropic directly** | No unified routing, no local gateway, no provider abstraction, no centralized logs                                        |
| **Use a generic proxy only**          | Basic forwarding is not enough if you also want routing policy, encrypted key management, and operator-friendly analytics |
| **Use FlowGate**                      | Keep one OpenAI-compatible endpoint while adding routing, logs, local security controls, and provider portability         |

## Why Pair It With FlowAPI

FlowGate and FlowAPI solve different layers of the cost stack:

| Layer                      | What optimizes it                                               |
| -------------------------- | --------------------------------------------------------------- |
| **Token unit price**       | [FlowAPI.net](https://flowapi.net) as the upstream endpoint     |
| **Token usage efficiency** | FlowGate's routing, request visibility, and local control plane |

If you are serious about cost control, you usually want both.

## Where The Savings Come From

FlowGate is not magic. It improves cost structure through a few concrete levers:

| Cost lever                       | What FlowGate changes                                                | Why it matters                                                          |
| -------------------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| **Model selection**              | Routes lower-complexity work to cheaper models                       | Prevents expensive models from handling trivial tasks                   |
| **Operational visibility**       | Exposes local logs, model usage, latency, and routing data           | Makes waste visible so teams can actually fix it                        |
| **Provider abstraction**         | Lets you point one app surface at different upstream providers       | Makes it easier to optimize for economics without rewriting client code |
| **Prompt discipline foundation** | Adds a local control layer for future prompt and skills optimization | Reduces the chance that token inefficiency stays hidden in agent stacks |

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

### 5. Analytics for finding your token assassins

FlowGate includes a built-in local dashboard so you can inspect:

- which models are used most often
- which providers consume the most tokens
- which requests are slow, error-prone, or over-routed
- how routing tiers are distributed over time

Cost optimization gets much easier once the waste is visible.

### 6. Skills-ready foundation

FlowGate includes optional skills-related configuration and package extras for teams exploring retrieval- and tool-oriented prompt optimization.

In the current repository, this is best understood as a foundation for prompt-efficiency work rather than a fully productized dynamic skill-routing system.

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

Go to <http://127.0.0.1:7798> and:

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

| Command               | Purpose                                                 |
| --------------------- | ------------------------------------------------------- |
| `flow-router start`   | Start the FastAPI server and static dashboard           |
| `flow-router add-key` | Interactively add a provider key to the encrypted vault |
| `flow-router version` | Print the installed FlowGate version                    |

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

| Document                                                   | Focus                                                                       |
| ---------------------------------------------------------- | --------------------------------------------------------------------------- |
| [docs/DESIGN.md](docs/DESIGN.md)                           | Design entry point and guide to the current documentation structure         |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)               | System layout, runtime components, request flow, and storage model          |
| [docs/API\_AND\_OPERATIONS.md](docs/API_AND_OPERATIONS.md) | API surface, auth flow, provider onboarding, and operational notes          |
| [docs/SMART\_ROUTER.md](docs/SMART_ROUTER.md)              | Smart-router strategies, config schema, API payloads, and fallback behavior |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)                 | Local development, frontend build flow, testing, and contribution notes     |
| [docs/TESTING.md](docs/TESTING.md)                         | Backend test coverage, smoke-test entry points, and verification guidance   |

## FAQ

### Is FlowGate a hosted proxy?

No. This repository is the local-first gateway layer you run yourself.

### Does FlowGate replace LiteLLM?

No. FlowGate uses LiteLLM as the forwarding layer and adds local routing, security, and observability on top.

### Does FlowGate require me to rewrite my OpenAI SDK integration?

Usually no. In most cases you only change the base URL and, if enabled, the caller token.

### Can I use FlowGate without FlowAPI.net?

Yes. FlowGate works independently with direct provider APIs and custom OpenAI-compatible endpoints. FlowAPI is an optional upstream pairing for better token pricing.

### Does FlowGate already implement full dynamic top-k skill injection?

Not as a finished production feature in the current repository. The project includes skills-related configuration and extension hooks, but the README positions this today as an optimization direction and foundation rather than a fully shipped headline workflow.

### Where do my logs and keys live?

Request metadata and catalog data live in local SQLite. Provider API keys are stored encrypted and unlocked only when needed.

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

## Roadmap

- [x] OpenAI-compatible local proxy
- [x] Encrypted provider vault
- [x] Model catalog sync
- [x] Smart router with rule-based and classifier modes
- [x] Local analytics dashboard
- [ ] Richer cost attribution across agents and workflows
- [ ] Better router evaluation and decision explainability
- [ ] Production-ready packaging and deployment examples
- [ ] Stronger admin auth and multi-user operations
- [ ] More polished benchmarking, demos, and screenshots

## Roadmap Direction

The current codebase suggests a clear next path for the project:

- broaden provider ergonomics for custom OpenAI-compatible gateways
- deepen router evaluation and cost/quality observability
- improve deployment and packaging workflows
- harden authentication and admin-session handling
- expand documentation and operator guidance

## Contributing

Pull requests are welcome.

Good contribution areas:

- provider integrations and OpenAI-compatible endpoint handling
- routing strategy improvements and classifier evaluation
- analytics and dashboard polish
- packaging, deployment, and operator workflows
- documentation, examples, and benchmark material

If you are extending behavior, keep the docs aligned with the implementation and prefer changes that remain inspectable and local-first.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=flowapi-net/flow-llm-router\&type=Date)](https://www.star-history.com/#flowapi-net/flow-llm-router\&Date)

## License

MIT
