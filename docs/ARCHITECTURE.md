# Architecture

This document describes how FlowGate is assembled at runtime and how requests move through the system.

## High-Level View

FlowGate combines four concerns in one local service:

- an OpenAI-compatible proxy
- an encrypted provider-key vault
- a local observability database
- a static operator dashboard

```text
Client SDK / Agent / Script
        |
        v
  FastAPI application
        |
        +--> Proxy endpoints (/v1/*)
        +--> Dashboard APIs (/api/*)
        +--> Static dashboard assets
        |
        +--> Smart router service
        +--> Vault
        +--> SQLite database
        |
        v
  LiteLLM + upstream providers
```

## Main Runtime Components

### FastAPI app

`flowgate.app:create_app()` builds the service and is responsible for:

- loading settings
- initializing the database
- attempting vault auto-unlock
- constructing the smart-router service
- registering API routers
- serving static frontend assets

### Proxy layer

The proxy lives in `src/flowgate/proxy/router.py`.

It exposes:

- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `GET /v1/models`

Its responsibilities are:

- validate caller tokens
- compute routing decisions
- resolve provider credentials
- translate requests into LiteLLM calls
- persist logs and usage metadata

### Vault

The vault is an in-process encryption layer that protects provider API keys at rest.

It works with:

- `vault_meta`: master-password metadata
- `provider_keys`: encrypted provider credentials
- persisted master key file for optional restart auto-unlock

The vault is attached at `app.state.vault`.

### Smart router service

`SmartRouterService` is attached at `app.state.smart_router_service`.

It chooses the model that should actually be used for a request based on:

- pass-through mode
- rule-based complexity scoring
- optional RouteLLM classifier routing

The service is intentionally local and synchronous for the decision step.

### Dashboard

The frontend is a Next.js application in `frontend/` that is statically exported and copied into `src/flowgate/static`.

FastAPI serves:

- `/_next` assets
- exported page HTML
- SPA fallbacks for dashboard routes

The dashboard is not a separate runtime service in production packaging; it is shipped with the API server.

## Request Flow

### Chat completions

For `POST /v1/chat/completions`, FlowGate executes the following path:

1. Read the caller token from `Authorization: Bearer ...` or the request body fallback.
2. Validate access against `caller_tokens`.
3. Ask the smart router for a `RoutingResult`.
4. Infer the provider from the routed model name.
5. Resolve provider API key and optional custom base URL from the vault.
6. Build LiteLLM request arguments.
7. Forward the request upstream.
8. Persist request and response metadata to `request_logs`.

For streaming requests, FlowGate forwards SSE chunks while still logging request metadata.

### Embeddings

For `POST /v1/embeddings`, FlowGate uses one of two paths:

- standard LiteLLM embedding call
- direct OpenAI-compatible JSON forwarding when a custom `api_base` is configured and LiteLLM provider inference would be unreliable

This avoids provider mismatches for some third-party OpenAI-compatible embedding gateways.

### Models

For `GET /v1/models`, FlowGate returns:

- synced provider models from `provider_models`, if available
- otherwise a minimal default model list

This keeps OpenAI-style clients usable even before the first catalog sync.

## Data Model

Core SQLModel tables:

| Table | Purpose |
| --- | --- |
| `vault_meta` | Stores vault salt and password verification hash |
| `provider_keys` | Stores encrypted provider keys and optional extra config such as custom base URL |
| `caller_tokens` | Stores hashed access tokens for FlowGate callers |
| `provider_models` | Stores model IDs discovered from provider `/models` endpoints |
| `router_config` | Stores dashboard-managed smart-router configuration |
| `request_logs` | Stores prompt, usage, latency, routing, and response metadata |

## Provider Resolution

Provider selection follows simple model-name inference rules first, such as:

- `gpt-*` -> `openai`
- `claude-*` -> `anthropic`
- `gemini-*` -> `google`
- `deepseek-*` -> `deepseek`

If the model name contains a provider prefix like `provider/model-name`, FlowGate uses the prefix directly.

When a provider key includes `extra_config` with `base_url`, FlowGate forwards to that OpenAI-compatible endpoint instead of the provider default.

## Configuration Layers

FlowGate configuration comes from three places:

1. built-in dataclass defaults
2. `flowgate.yaml` or `flowgate.yml`
3. in-memory state initialized from SQLite for router settings

YAML supports `${ENV_VAR}` substitution for string values.

Smart-router config is special:

- YAML provides the initial default
- the dashboard writes router config to SQLite
- SQLite wins on subsequent startups if a saved row exists

## Security Model

FlowGate separates three security boundaries:

### Caller authorization

Caller tokens decide who may use the proxy.

- no caller tokens configured -> proxy remains open
- one or more caller tokens configured -> valid token required

### Provider credential protection

Provider API keys are encrypted before being written to SQLite and decrypted only when needed for outbound calls.

### Network access control

IP filtering is enforced by middleware and supports:

- `local_only`
- `whitelist`
- `open`

## Frontend-to-Backend Contract

The dashboard talks only to FlowGate's own REST API.

Main dashboard domains:

- auth and vault setup
- provider keys
- caller tokens
- logs and analytics
- model catalog sync
- smart-router configuration
- integration guidance

Because the frontend is a static export, most runtime behavior is implemented in the API layer rather than in a server-rendered frontend.

## Packaging Notes

The Python package includes:

- backend code from `src/flowgate`
- CLI entrypoint `flow-router`
- static dashboard files copied into `src/flowgate/static`

The expected workflow is:

1. build the frontend
2. copy static output into the package
3. run FlowGate as a single Python service

## Extension Points

The current codebase is easiest to extend in these areas:

- provider inference and provider catalog defaults
- smart-router strategies and scoring rules
- dashboard pages and APIs
- request analytics and aggregation
- additional hardening around admin auth and session handling
