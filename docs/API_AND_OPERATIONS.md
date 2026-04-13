# API And Operations

This document covers the public API surface, the operator workflow, and the most important runtime behaviors for running FlowGate locally or on a private server.

## Base URLs

Default local addresses:

- dashboard: `http://127.0.0.1:7798`
- proxy API: `http://127.0.0.1:7798/v1`
- FastAPI docs: `http://127.0.0.1:7798/docs`

## Operator Workflow

Typical first-run flow:

1. start FlowGate
2. open the dashboard
3. set a master password if the vault is not initialized
4. unlock the vault
5. add provider keys
6. optionally sync provider models
7. optionally create caller tokens
8. point clients to FlowGate's `/v1` base URL

## Authentication Model

FlowGate uses two different token systems:

### Admin auth token

This token is created after verifying the vault master password through `/api/auth/verify`.

It is used for protected dashboard mutations such as:

- adding or editing provider keys
- creating caller tokens
- updating IP allowlists
- updating smart-router configuration
- syncing provider models

### Caller token

This token is used by applications that call the proxy itself.

It is sent through:

- `Authorization: Bearer <token>`
- or the request body's `user` field fallback for some OpenAI-client flows

Important behavior:

- if there are no caller tokens in the database, the proxy is open
- once caller tokens exist, valid caller tokens are required

## Proxy API

### `POST /v1/chat/completions`

OpenAI-compatible chat completions endpoint.

Capabilities:

- streaming and non-streaming
- tools-related fields passed through to LiteLLM
- model rerouting via smart router
- request logging into SQLite

Minimal example:

```bash
curl http://127.0.0.1:7798/v1/chat/completions \
  -H "Authorization: Bearer fgt_your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### `POST /v1/embeddings`

OpenAI-compatible embeddings endpoint.

FlowGate supports:

- standard LiteLLM embedding forwarding
- direct JSON forwarding for custom OpenAI-compatible gateways when needed

### `GET /v1/models`

Returns model data in an OpenAI-style list format.

Behavior:

- if provider models have been synced, return those
- otherwise return a small built-in fallback list

## Auth API

Base path: `/api/auth`

### `GET /api/auth/status`

Returns vault state:

- whether the vault has been initialized
- whether it is currently unlocked

### `POST /api/auth/setup`

Initializes the vault with a master password.

Notes:

- works only once for a fresh database
- persists vault metadata
- attempts to persist the derived master key for future auto-unlock

### `POST /api/auth/verify`

Verifies the master password and returns a temporary admin auth token.

This endpoint also unlocks the vault in memory if needed.

## Provider Key API

Base path: `/api/keys`

### `GET /api/keys`

Lists provider entries with masked key suffixes.

### `POST /api/keys`

Adds a new provider key.

Required fields:

- `provider`
- `key_name`
- `api_key`

Optional:

- `extra_config` JSON string, commonly used for `base_url`

Example payload:

```json
{
  "provider": "siliconflow",
  "key_name": "siliconflow-default",
  "api_key": "sk-...",
  "extra_config": "{\"base_url\":\"https://api.siliconflow.cn/v1\"}"
}
```

### `PUT /api/keys/{key_id}`

Updates:

- label
- API key
- `extra_config`
- enabled state

### `DELETE /api/keys/{key_id}`

Deletes a provider key and removes it from the in-memory vault cache.

## Caller Token API

Base path: `/api/caller-tokens`

### `GET /api/caller-tokens`

Lists caller tokens with metadata such as:

- name
- enabled flag
- prefix
- creation time
- last-used timestamp

### `POST /api/caller-tokens`

Creates a caller token and returns the plaintext token **once**.

### `PUT /api/caller-tokens/{token_id}`

Allows updating:

- `name`
- `enabled`

### `DELETE /api/caller-tokens/{token_id}`

Removes the caller token permanently.

## Model Catalog API

Base path: `/api/models`

### `GET /api/models`

Returns the locally synced provider catalog.

### `POST /api/models/sync/{provider_name}`

Fetches the provider's `/models` endpoint and upserts results into SQLite.

Behavior notes:

- requires the vault to be unlocked
- resolves base URL from provider `extra_config` first
- otherwise falls back to built-in defaults for known providers

## Logs And Analytics API

Base path: `/api`

### `GET /api/stats/overview`

Returns high-level KPIs such as:

- total requests
- prompt tokens
- completion tokens
- average latency
- success rate
- error count

### `GET /api/stats/timeline`

Returns request and token usage grouped by hour or day.

### `GET /api/stats/providers`

Returns request and token usage grouped by provider.

### `GET /api/stats/models`

Returns top models by request count.

### `GET /api/logs`

Returns paginated request log summaries.

### `GET /api/logs/{log_id}`

Returns full request log detail, including routing metadata and stored prompt/response content when logging is enabled.

## Server Config And IP Controls

### `GET /api/server-config`

Returns a non-sensitive subset of runtime config for the frontend.

### `GET /api/security/ip-whitelist`

Returns the active IP access-control state.

### `PUT /api/security/ip-whitelist`

Updates:

- `enabled`
- `mode`
- `allowed_ips`

Valid modes:

- `local_only`
- `whitelist`
- `open`

## Operational Notes

### Provider onboarding

Recommended order:

1. unlock the vault
2. add provider key
3. set a custom `base_url` only when the provider is not covered by built-in defaults
4. sync models
5. use synced models in router mappings or clients

### Logging behavior

Logging is controlled by `logging` settings:

- `log_prompts`
- `log_responses`
- `redact_secrets`

If prompt logging is disabled, the stored request body becomes `[redacted]`.

### Vault auto-unlock

FlowGate attempts startup unlock in this order:

1. persisted master key file
2. `FLOWGATE_MASTER_PASSWORD` environment variable

If neither works, the vault stays locked until a user verifies the master password.

### Provider base URLs

Custom OpenAI-compatible endpoints are stored in `ProviderKey.extra_config` and reused for:

- request forwarding
- model sync
- MF embedding integration

### Access-control reminder

For local experimentation, open access may be acceptable. For any shared environment:

- create at least one caller token
- keep IP mode at `local_only` or `whitelist`
- use `redact_secrets: true`

## Troubleshooting

### Proxy returns `401 Invalid or missing FlowGate access token`

Likely causes:

- caller tokens exist and the request does not include a valid one
- the wrong token was used
- the token was disabled or deleted

### Provider sync fails with `Vault is locked`

Unlock the vault first through the dashboard or `/api/auth/verify`.

### Router classifier silently behaves like rule-based routing

Expected reasons include:

- RouteLLM extra not installed
- classifier initialization failed
- classifier scoring failed and FlowGate fell back to complexity routing

### Requests fail against a custom provider

Check:

- provider name
- `extra_config.base_url`
- whether the upstream is really OpenAI-compatible
- whether the stored API key belongs to that endpoint
