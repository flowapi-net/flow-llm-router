# Development

This document covers local setup, frontend build flow, test entry points, and practical notes for contributors.

## Prerequisites

- Python `3.10+`
- Node.js `18+` for frontend work
- a virtual environment tool of your choice

Optional:

- RouteLLM dependencies for classifier work
- provider credentials if you want to run end-to-end proxy tests

## Local Setup

```bash
git clone <your-repo-url>
cd flow-llm-router
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,classifier]'
```

If you do not need classifier routing locally:

```bash
pip install -e '.[dev]'
```

## Backend Entry Points

### CLI

```bash
flow-router start
```

Useful flags:

- `--host`
- `--port`
- `--config`
- `--reload`

### App factory

FlowGate uses the FastAPI app factory:

```bash
uvicorn flowgate.app:create_app --factory --reload
```

The CLI is still the most accurate way to run the project because it mirrors vault-unlock startup behavior more closely.

## Configuration During Development

Create a local config file from the example:

```bash
cp flowgate.yaml.example flowgate.yaml
```

Common things to adjust for local work:

- server port
- SQLite database path
- log settings
- smart-router defaults
- IP mode if you need non-local access

YAML values support `${ENV_VAR}` substitution.

## Frontend Workflow

The dashboard source lives in `frontend/` and is built as a static export.

### Install frontend dependencies

```bash
cd frontend
npm ci
```

### Run the frontend in development mode

```bash
npm run dev
```

### Build the frontend

```bash
npm run build
```

### Copy the static build into the Python package

From the repository root:

```bash
bash scripts/build_frontend.sh
```

This script:

1. runs `npm ci`
2. runs `npm run build`
3. copies `frontend/out/*` into `src/flowgate/static/`

If you modify the dashboard and want the FastAPI app to serve the updated UI, rebuilding and copying the static export is required.

## Test Suite

### Unit tests

Run the Python tests:

```bash
pytest -q
```

The current test suite covers areas such as:

- configuration loading
- database behavior
- security and vault flow
- analytics endpoints
- proxy behavior
- smart-router logic

### Focused router tests

```bash
pytest tests/test_smart_router.py -q
```

### Integration script

There is also a manual integration helper:

```bash
python scripts/test_service.py --base http://127.0.0.1:7798
```

Useful variants:

```bash
python scripts/test_service.py --suite health
python scripts/test_service.py --suite proxy --token fgt_xxx --model gpt-4o-mini
python scripts/test_service.py --suite embed --token fgt_xxx --embed-model text-embedding-3-small
```

This script is best used for smoke testing a running service rather than as a strict CI-grade test harness.

## Suggested Development Loops

### Backend-only changes

```bash
flow-router start --reload
pytest -q
```

### Router changes

```bash
pytest tests/test_smart_router.py -q
flow-router start --reload
```

Then verify:

- `/api/router/config`
- `/api/router/test`
- router page behavior in the dashboard

### Frontend changes

```bash
cd frontend
npm run dev
```

After validating the UI, run:

```bash
bash scripts/build_frontend.sh
```

## Code Organization

Top-level structure:

| Path | Purpose |
| --- | --- |
| `src/flowgate/app.py` | App factory and startup lifecycle |
| `src/flowgate/cli.py` | CLI entrypoints |
| `src/flowgate/config.py` | YAML-backed settings dataclasses |
| `src/flowgate/api/` | Dashboard and admin REST endpoints |
| `src/flowgate/proxy/` | OpenAI-compatible proxy endpoints |
| `src/flowgate/security/` | Vault, IP guard, redaction, persisted master key handling |
| `src/flowgate/smart_router/` | Rule-based and classifier routing logic |
| `src/flowgate/db/` | SQLModel schema and DB helpers |
| `frontend/` | Next.js dashboard source |
| `tests/` | Python tests |
| `scripts/` | Helper scripts for frontend build and service smoke tests |

## Contribution Guidelines

When making changes:

- keep docs aligned with actual runtime behavior
- prefer incremental, inspectable changes
- update tests when behavior changes materially
- avoid documenting features that are not implemented in this repository

Areas where documentation especially needs to stay in sync:

- smart-router payload shape
- vault and auth behavior
- model sync behavior
- frontend build and packaging flow

## Common Pitfalls

### Frontend changes do not appear in the packaged app

You probably updated `frontend/` but did not run `bash scripts/build_frontend.sh`.

### Provider sync or proxy calls fail even though the key exists

Check whether:

- the vault is unlocked
- the provider entry is enabled
- the custom base URL is correct

### Smart-router docs drift easily

The router has both YAML-facing config and dashboard-facing API config. Keep both aligned with:

- `src/flowgate/config.py`
- `src/flowgate/smart_router/service.py`
- `src/flowgate/api/router_config.py`

## Release Readiness Checklist

Before shipping a meaningful change set, it is worth checking:

- `pytest -q`
- any focused test file for the changed subsystem
- frontend build succeeds if UI changed
- static dashboard copy step succeeds if UI changed
- relevant docs remain accurate
