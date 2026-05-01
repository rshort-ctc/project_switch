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

Start PostgreSQL, Redis, Qdrant, the API, the network web surface, and the host dashboard:

```bash
scripts/switch start
```

The start command builds images first when needed. To stop the full local stack:

```bash
scripts/switch stop
```

Useful lifecycle commands:

```bash
scripts/switch status
scripts/switch logs
scripts/switch logs switch-api
scripts/switch restart
```

To start only the host dashboard stack:

```bash
scripts/switch start --desktop
```

Dashboard mode starts PostgreSQL, Redis, Qdrant, migrations, the API, and the
`switch-dashboard` container on the host dashboard port.

The current Compose file keeps data services and the API local-only while exposing a limited web surface for LAN clients:
- Switch API on `127.0.0.1:55600`
- Switch host dashboard on `127.0.0.1:55601`
- Switch network web surface on `0.0.0.0:55602`
- PostgreSQL on `127.0.0.1:55632`
- Redis on `127.0.0.1:55637`
- Qdrant on `127.0.0.1:55633` and `127.0.0.1:55634`

Repository registration validates paths inside the backend process. When the
backend runs in Docker, selected host repositories must be mounted into the API
container. `scripts/switch` defaults `SWITCH_HOST_REPO_ROOT` to
`$HOME/Projects` and mounts that path read-only at the same absolute path, so
repos under `~/Projects` can be selected from the desktop directory picker. Set
`SWITCH_HOST_REPO_ROOT` before starting Switch if your repos live elsewhere:

```bash
SWITCH_HOST_REPO_ROOT=/path/to/repos scripts/switch start --desktop
```

Service names in Compose:
- `switch-api`
- `switch-web`
- `switch-db`
- `switch-redis`
- `switch-qdrant`
- optional `switch-vllm`

If a previous SWITCH Compose project used older service names or host port
defaults, Docker may report orphan containers or a host port collision. Run
`docker compose down --remove-orphans` before starting the renamed stack, or set
`SWITCH_POSTGRES_PORT` to an unused local port. Container-to-container database
traffic remains `switch-db:5432`.

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
- `SWITCH_OLLAMA_ENDPOINT`
- `SWITCH_ARTIFACT_ROOT`
- `SWITCH_WORKSPACE_ROOT`
- `SWITCH_MODEL_REQUEST_TIMEOUT_SECONDS`
- `SWITCH_MODEL_MAX_RETRIES`
- `SWITCH_MODEL_RETRY_BACKOFF_SECONDS`
- `SWITCH_ALLOW_OLLAMA_CLOUD_MODELS`
- `SWITCH_PLANNER_MODEL`
- `SWITCH_CODER_MODEL`
- `SWITCH_REVIEWER_MODEL`
- `SWITCH_SUMMARIZER_MODEL`
- `SWITCH_EMBEDDING_MODEL`
- `SWITCH_RERANKER_MODEL`
- `SWITCH_PROTECTED_BRANCHES`
- `SWITCH_ALLOWED_NETWORK_CIDRS`
- `SWITCH_ALLOWED_REPO_ROOTS`

Local-only operation requires public network access to remain disabled.

## Run API

```bash
uvicorn app.main:create_app --factory --reload
```

Current health endpoint:

```bash
curl http://127.0.0.1:55600/health
```

Current model gateway health endpoint:

```bash
curl http://127.0.0.1:55600/model-gateway/health
```

This endpoint expects a local vLLM-compatible server at `SWITCH_VLLM_ENDPOINT`.

Confirm PostgreSQL health:

```bash
docker compose exec switch-db pg_isready -U switch -d switch
```

Confirm Qdrant health:

```bash
curl http://127.0.0.1:55633/collections
```

Confirm Redis health:

```bash
docker compose exec switch-redis redis-cli ping
```

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
- Host dashboard: `http://127.0.0.1:55601`
- Network web surface: `http://<host-lan-ip>:55602`
- Desktop shell: `dashboard/src-tauri`

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
make dashboard-desktop-check
make dashboard-desktop-dev
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

## Desktop Shell

The desktop shell is a Tauri wrapper around the local dashboard. It does not run
agent logic or shell commands itself; it connects to the same backend APIs and
policy gates as the browser dashboard.

The chat console runs Python snippets through the backend sandbox runner. It
mounts an isolated scratch workspace, disables network by default, does not pass
host secrets, and uses the configured Docker/Podman engine. A containerized API
does not mount the host Docker socket by default, so sandbox execution requires
running the backend where Docker or Podman is available or adding a separately
approved sandbox worker.

Start both UI surfaces with the local services:

```bash
scripts/switch start
```

Use this command to compile-check the Rust/Tauri shell without opening a window:

```bash
cd dashboard
npm run desktop:check
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

Register and index a repo through the CLI once the API is running:

```bash
switch repo add /absolute/path/to/repo --name my-repo
switch repo index <repo-id>
switch repo status <repo-id>
```

`switch repo index` writes durable index status to PostgreSQL and semantic code
chunks to the local Qdrant collection. Configure a local embedding model first:

```bash
export SWITCH_EMBEDDING_MODEL=<local-embedding-model>
```

The production API no longer uses deterministic test embeddings for repo Q&A.
If Qdrant or the local embedding endpoint is unavailable, indexing and semantic
retrieval fail with a clear service error.

## Task Workflow Smoke Test

Create and run a coding task through the API-backed CLI:

```bash
switch task create <repo-id> "Fix greeting" \
  --description "Inspect the repo and stop before mutation." \
  --created-by <user-id>
switch task run <task-id>
switch task status <task-id>
switch task logs <task-id>
```

`switch task run` calls `POST /tasks/{task_id}/run`; it does not run workflow
logic in the CLI process. The current API uses FastAPI `BackgroundTasks` as a
temporary local executor. This means task activity begins in the API process
today and should move to the Redis-backed worker runtime in the worker phase.

Inspect pending approvals with:

```bash
curl http://127.0.0.1:55600/approvals/pending
```

Task status includes latest run status, current or last workflow state, agent
step count, tool-call count, pending approval count, and latest failure text
when available.

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

Run a sample retrieval-style question through the API-backed CLI:

```bash
switch ask <repo-id> "Where is authentication handled?"
```

`switch ask` requires a ready index. If the repository has not been indexed,
the backend returns `409 Conflict` and the CLI tells you to run:

```bash
switch repo index <repo-id>
```

When `SWITCH_SUMMARIZER_MODEL`, `SWITCH_PLANNER_MODEL`, or
`SWITCH_CODER_MODEL` is configured, `/ask` asks the local model gateway to answer
from retrieved context only. Without a configured or reachable answer model,
responses are marked `degraded=true` and show context citations only.

Troubleshooting:
- Confirm Qdrant: `curl http://127.0.0.1:55633/collections`
- Confirm model gateway: `curl http://127.0.0.1:55680/v1/models`
- Rebuild stale vectors: rerun `switch repo index <repo-id>`
