# Smart Router

FlowGate's smart router is a **local routing policy layer** that decides which model should actually serve a request before the proxy forwards it upstream.

It does not replace LiteLLM or build a new inference backend. Instead, it adds an operator-controlled decision layer on top of FlowGate's OpenAI-compatible proxy.

## Design Goals

- keep routing local and inspectable
- support both fast heuristics and stronger learned classifiers
- use one shared tier-to-model mapping across strategies
- allow hot reload from the dashboard without restarting the server
- degrade safely when optional classifier dependencies are missing

## Runtime Layout

```text
Dashboard /router
       |
       | GET/PUT /api/router/config
       v
SmartRouterService
       |
       +--> ComplexityScorer
       |
       +--> RouteLLM controller (optional)
       |
       v
RoutingResult(model, tier, score, original_model)
       |
       v
/v1/chat/completions -> LiteLLM -> provider
```

The service is initialized on startup and attached to `app.state.smart_router_service`.

## Routing Modes

### `off`

Pass-through mode:

- the requested model is used unchanged
- the returned routing tier is `DIRECT`
- no routing score is persisted in request logs

### `complexity`

Rule-based prompt routing powered by `ComplexityScorer`.

Characteristics:

- fully local
- no extra package dependency
- very low overhead
- four routing tiers
- configurable weights and boundaries

Default tier flow:

```text
0.00 ---- 0.25 ---- 0.50 ---- 0.75 ---- 1.00
 SIMPLE    MEDIUM    COMPLEX   REASONING
```

### `classifier`

Classifier-based routing powered by RouteLLM when installed with:

```bash
pip install 'flow-llm-router[classifier]'
```

Characteristics:

- uses RouteLLM routers such as `bert`, `mf`, `sw_ranking`, or `causal_llm`
- scores a prompt with `calculate_strong_win_rate()`
- maps the resulting score back into the same four FlowGate tiers
- reuses the same `tiers` mapping as the rule-based strategy

Important behavior:

- if RouteLLM is not installed, FlowGate falls back to `complexity`
- if classifier routing fails at runtime, FlowGate falls back to `complexity`
- classifier routing in FlowGate is **not** exposed as separate strong/weak model fields in the UI API; it still routes through `SIMPLE`, `MEDIUM`, `COMPLEX`, and `REASONING`

## Complexity Strategy

The rule-based scorer evaluates only **user** messages and computes a score in the range `[0.0, 1.0]`.

Default dimensions:

| Dimension | Default weight | Notes |
| --- | --- | --- |
| `tokenCount` | `0.15` | More content usually implies more work. |
| `codePresence` | `0.20` | Looks for programming and implementation keywords. |
| `reasoningMarkers` | `0.25` | Two or more strong reasoning markers immediately push the score to `1.0`. |
| `technicalTerms` | `0.15` | Detects advanced technical vocabulary. |
| `simpleIndicators` | `0.15` | Negative signal for simple prompts such as greetings or definitions. |
| `multiStepPatterns` | `0.05` | Detects multi-step instructions and sequences. |
| `questionComplexity` | `0.05` | Gives a boost for multi-question prompts. |

Scoring properties:

- empty or non-user-only input returns `0.0`
- multipart content arrays are supported when the content parts are text
- the final score is clamped to `[0.0, 1.0]`

## Classifier Strategy

FlowGate wraps RouteLLM behind `SmartRouterService`.

Classifier flow:

1. Concatenate non-system prompt text into a single routing string.
2. Call the selected RouteLLM router's `calculate_strong_win_rate()`.
3. Map the score into FlowGate's four tiers using `classifier_tier_boundaries`.
4. Resolve the final target model from the shared `tiers` mapping.

### Supported classifier types

The code currently accepts RouteLLM router names such as:

- `bert`
- `mf`
- `sw_ranking`
- `causal_llm`

### MF embedding behavior

The `mf` router may require OpenAI-compatible embedding access. FlowGate supports this in two ways:

- via YAML fields such as `mf_embedding_base_url` and `mf_embedding_api_key`
- via model-catalog-derived credentials applied from the FlowGate vault

The dashboard API intentionally does **not** persist embedding API secrets from the client payload. Secrets must come from server-side configuration or the provider vault.

## Configuration Model

The smart-router configuration is represented by `SmartRouterConfig`.

Current effective fields:

```python
@dataclass
class SmartRouterConfig:
    enabled: bool = False
    strategy: str = "complexity"  # complexity | classifier | off

    tiers: dict[str, str]
    tier_boundaries: dict[str, float]
    dimension_weights: dict[str, float]

    classifier_type: str = "bert"
    classifier_tier_boundaries: dict[str, float]

    mf_embedding_base_url: str = ""
    mf_embedding_api_key: str = ""
    mf_embedding_model: str = ""
```

### Shared model mapping

Both routing strategies use the same tier mapping:

```yaml
tiers:
  SIMPLE: gpt-4o-mini
  MEDIUM: gpt-4o
  COMPLEX: claude-sonnet
  REASONING: o1-preview
```

This gives operators one consistent place to decide which model corresponds to each workload level.

## YAML Example

```yaml
smart_router:
  enabled: true
  strategy: complexity             # complexity | classifier | off
  tiers:
    SIMPLE: gpt-4o-mini
    MEDIUM: gpt-4o
    COMPLEX: claude-sonnet
    REASONING: o1-preview
  tier_boundaries:
    simple_medium: 0.25
    medium_complex: 0.50
    complex_reasoning: 0.75

  # Optional, otherwise built-in defaults are used
  # dimension_weights:
  #   tokenCount: 0.15
  #   codePresence: 0.20
  #   reasoningMarkers: 0.25
  #   technicalTerms: 0.15
  #   simpleIndicators: 0.15
  #   multiStepPatterns: 0.05
  #   questionComplexity: 0.05

  # Classifier-specific options
  # classifier_type: bert
  # classifier_tier_boundaries:
  #   simple_medium: 0.28
  #   medium_complex: 0.40
  #   complex_reasoning: 0.50
  # mf_embedding_base_url: https://api.openai.com/v1
  # mf_embedding_api_key: ${OPENAI_API_KEY}
  # mf_embedding_model: text-embedding-3-small
```

## Config Source of Truth

At startup, FlowGate loads router settings in this order:

1. `router_config` row in SQLite if a saved dashboard config exists
2. `smart_router` from `flowgate.yaml`
3. built-in defaults

This means dashboard edits override YAML on subsequent runs.

## Request Path

For `POST /v1/chat/completions`, the request path is:

1. validate caller token
2. obtain `SmartRouterService`
3. call `service.route(messages, requested_model)`
4. infer provider from the routed model
5. resolve provider key and optional base URL from the vault
6. forward to LiteLLM
7. persist routing score and tier into `request_logs` when routing was active

If routing is disabled, `DIRECT` is returned and the routing fields remain `NULL` in the log table.

## Dashboard Behavior

The dashboard page at `/router` provides:

- strategy selection
- tier-to-model mapping
- complexity boundary editing
- dimension-weight editing
- classifier-type selection
- live route testing
- historical routing stats

Saving configuration triggers:

1. `PUT /api/router/config`
2. live service reload in memory
3. persistence to the singleton `router_config` table
4. immediate use by new requests

No process restart is required.

## Router API

All smart-router endpoints live under `/api/router`.

### `GET /api/router/config`

Returns the active configuration in dashboard-friendly shape.

Example response:

```json
{
  "success": true,
  "data": {
    "enabled": true,
    "strategy": "complexity",
    "complexity": {
      "tiers": {
        "SIMPLE": "gpt-4o-mini",
        "MEDIUM": "gpt-4o",
        "COMPLEX": "claude-sonnet",
        "REASONING": "o1-preview"
      },
      "tier_boundaries": {
        "simple_medium": 0.25,
        "medium_complex": 0.5,
        "complex_reasoning": 0.75
      },
      "dimension_weights": {
        "tokenCount": 0.15,
        "codePresence": 0.2,
        "reasoningMarkers": 0.25,
        "technicalTerms": 0.15,
        "simpleIndicators": 0.15,
        "multiStepPatterns": 0.05,
        "questionComplexity": 0.05
      }
    },
    "classifier": {
      "type": "bert",
      "tier_boundaries": {
        "simple_medium": 0.28,
        "medium_complex": 0.4,
        "complex_reasoning": 0.5
      },
      "available": false,
      "mf_embedding_model": ""
    }
  }
}
```

### `PUT /api/router/config`

Requires a valid admin auth token.

Behavior:

- validates the payload
- strips client-supplied MF embedding secrets
- reloads `SmartRouterService`
- persists the resulting config to SQLite

### `POST /api/router/test`

Tests routing without making an upstream LLM call.

Example request:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Design a distributed microservice architecture with strong failure isolation."
    }
  ],
  "model": "gpt-4o"
}
```

Example response:

```json
{
  "success": true,
  "data": {
    "strategy": "complexity",
    "score": 0.62,
    "tier": "COMPLEX",
    "routed_model": "claude-sonnet",
    "original_model": "gpt-4o",
    "latency_us": 340
  }
}
```

### `GET /api/router/stats?days=7`

Aggregates routing metadata from `request_logs` and returns:

- per-tier distribution
- daily trend data
- total number of routed requests

## Storage Model

### `router_config`

Singleton table used to persist dashboard router configuration:

```sql
CREATE TABLE router_config (
    id          INTEGER PRIMARY KEY,
    enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    strategy    TEXT NOT NULL DEFAULT 'complexity',
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMP
);
```

### `request_logs`

Routing-related columns:

- `model_requested`
- `model_used`
- `complexity_score`
- `complexity_tier`

Even classifier-based routing uses the same `complexity_score` and `complexity_tier` fields so the analytics pipeline remains simple.

## Failure and Fallback Rules

FlowGate favors continuity over strict classifier correctness:

- missing RouteLLM package -> fall back to `complexity`
- classifier initialization error -> fall back to `complexity`
- classifier scoring failure -> fall back to `complexity`
- disabled router or `strategy=off` -> return `DIRECT`

This keeps the proxy usable even when optional router features are unavailable.

## Operator Guidance

Use `complexity` when:

- you want zero extra routing dependencies
- you care most about latency and simplicity
- your prompt mix is mostly engineering and product workloads

Use `classifier` when:

- you want more semantic routing behavior
- you can install RouteLLM and support its dependencies
- you want to experiment with learned routing policies while keeping a safe local fallback
