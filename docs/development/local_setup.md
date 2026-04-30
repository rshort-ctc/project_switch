# Local Development Setup

## Prerequisites

Target runtime:
- Python 3.12+
- Docker or Podman
- ripgrep
- git

Current validation note:
- The local workspace used for this recon has Python 3.13.13 available.
- `python3.12` was not available in this environment.
- The project remains configured for Python 3.12+.

## Install

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

If `python3.12` is not installed locally, use another Python version compatible with `requires-python = ">=3.12"`.

## Local Services

Start PostgreSQL, Redis, and Qdrant:

```bash
docker compose up -d
```

The current Compose file exposes:
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- Qdrant on `localhost:6333` and `localhost:6334`

## Environment

Settings are read from environment variables with the `SWITCH_` prefix.
Copy `.env.example` to `.env` for local development when you need to override defaults.

Current settings include:
- `SWITCH_APP_NAME`
- `SWITCH_ENVIRONMENT`
- `SWITCH_LOCAL_ONLY`
- `SWITCH_LOG_LEVEL`
- `SWITCH_LOG_JSON`
- `SWITCH_DOCS_URL`
- `SWITCH_REDOC_URL`
- `SWITCH_OPENAPI_URL`
- `SWITCH_DATABASE_URL`
- `SWITCH_REDIS_URL`
- `SWITCH_VECTOR_STORE_URL`
- `SWITCH_VLLM_ENDPOINT`
- `SWITCH_MODEL_REQUEST_TIMEOUT_SECONDS`
- `SWITCH_MODEL_MAX_RETRIES`
- `SWITCH_MODEL_RETRY_BACKOFF_SECONDS`
- `SWITCH_PLANNER_MODEL`
- `SWITCH_CODER_MODEL`
- `SWITCH_REVIEWER_MODEL`
- `SWITCH_SUMMARIZER_MODEL`
- `SWITCH_EMBEDDING_MODEL`
- `SWITCH_RERANKER_MODEL`
- `SWITCH_PROTECTED_BRANCHES`
- `SWITCH_ALLOWED_NETWORK_CIDRS`

Local-only operation requires public network access to remain disabled.

## Run API

```bash
uvicorn app.main:create_app --factory --reload
```

Current health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Current model gateway health endpoint:

```bash
curl http://127.0.0.1:8000/model-gateway/health
```

This endpoint expects a local vLLM-compatible server at `SWITCH_VLLM_ENDPOINT`.

## Test

```bash
pytest
```

## Lint

```bash
ruff check .
```

## Format

```bash
ruff format .
```

## Typecheck

```bash
mypy app
```

## Current Entrypoints

- API factory: `app.main:create_app`
- ASGI app: `app.main:app`

## Development Commands

The same operations are available through `make` and `scripts/`:

```bash
make install
make format
make lint
make typecheck
make test
make migrate
make run
```

```bash
bash scripts/install
bash scripts/format
bash scripts/lint
bash scripts/typecheck
bash scripts/test
bash scripts/migrate
bash scripts/run
```

## Migrations

Run migrations against the configured `SWITCH_DATABASE_URL`:

```bash
alembic upgrade head
```

For local migration smoke tests without PostgreSQL:

```bash
SWITCH_DATABASE_URL=sqlite+pysqlite:///./local-migration-smoke.db alembic upgrade head
```

## Development Notes

This project should not depend on cloud LLM APIs, hosted code assistants, or hosted vector databases. Local vLLM-compatible inference is the expected model boundary.

## Indexer Smoke Test

The indexer tests create a small local git repository and validate:
- ignored files are skipped
- binary/vendor/secret files are skipped
- exact search uses ripgrep
- symbol search finds extracted functions/classes/exports
- semantic search uses the local embedder interface
- unchanged file hashes are skipped during incremental reindex

Run:

```bash
pytest tests/test_indexing.py
```

## Retrieval Smoke Test

The retrieval tests create local git repositories and validate:
- bug-like queries retrieve relevant source and test files
- context bundles retain file and line provenance
- exact, symbol, semantic, file path, import/export, git history, and test-pairing lanes contribute
- overlapping chunks are deduplicated
- context budget enforcement works
- ignored and secret-looking files are not returned

Run:

```bash
pytest tests/test_retrieval.py
```
