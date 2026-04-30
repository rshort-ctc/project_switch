# SWITCH

SWITCH is a fully local, employer-grade coding agent platform. The project is intended to run without cloud LLM APIs, without hosted code assistants, and without source code or secrets leaving the local machine or approved local network.

## Repository Status

This is a local coding-agent platform foundation through the internal dashboard phase. It is
not yet a complete autonomous coding-agent application.

Current baseline:
- Python package: `switch-agent`
- Runtime target: Python 3.12+
- Backend framework: FastAPI
- Config: Pydantic Settings with `SWITCH_` environment variables
- Logging: stdlib structured JSON logging
- Database ORM: SQLAlchemy 2
- Migrations: Alembic
- Model gateway: local vLLM-compatible HTTP client
- Tests: pytest
- Lint/format: Ruff
- Type checking: mypy strict mode
- Local services: PostgreSQL, Redis, and Qdrant via Docker Compose
- Dashboard: Next.js internal operations UI under `dashboard/`

Existing source layout:
- `app/main.py`: FastAPI app factory and ASGI app
- `app/api/`: API router and route modules
- `app/core/`: environment-driven settings and structured logging
- `app/schemas/`: response schemas
- `app/db/`: SQLAlchemy base, sessions, and repositories
- `app/models/`: durable entities and status enums
- `app/services/`: persistence, audit, run, and tool-call services
- `app/security/`: local security helpers, including secret redaction
- `app/model_gateway/`: provider-agnostic local model gateway
- `app/indexing/`: local repository crawler, symbol extractor, chunker, exact search, embedding pipeline, and vector-store boundary
- `app/agents/`, `app/tools/`, `app/sandbox/`: package boundaries reserved for later phases
- `alembic/`: database migrations
- `tests/`: configuration, logging, health, version, migration, and persistence tests
- `docker-compose.yml`: local PostgreSQL, Redis, and Qdrant services
- `scripts/` and `Makefile`: local development commands
- `dashboard/`: internal web dashboard that consumes backend APIs only

## Local-Only Position

SWITCH assumes:
- Inference is provided by a local vLLM-compatible endpoint.
- Cloud LLM APIs are not used.
- Source code, prompts containing source code, secrets, repository metadata, embeddings, and audit logs remain local.
- PostgreSQL stores durable task, run, approval, and audit state.
- Qdrant or pgvector stores local embeddings.
- Redis is used for local queues and cache.
- Docker or Podman sandboxes execute validation and build commands.
- Human approval is required before write, push, or PR-producing actions.
- Tool calls are audited.

## Development

See [docs/development/local_setup.md](docs/development/local_setup.md).

Quick validation:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
ruff check .
mypy app
pytest
```

Run migrations:

```bash
alembic upgrade head
```

Run the current API:

```bash
uvicorn app.main:create_app --factory --reload
```

Run the dashboard:

```bash
cd dashboard
npm install
npm run dev
```

Current endpoints:
- `GET /health`
- `GET /health/details`
- `GET /version`
- `GET /model-gateway/health`
- `GET /agent/models`
- `GET /repos`
- `POST /repos`
- `POST /repos/{repository_id}/index`
- `GET /repos/{repository_id}/status`
- `GET /tasks`
- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/logs`
- `GET /tasks/{task_id}/diff`
- `GET /tasks/{task_id}/validations`
- `GET /approvals/pending`
- `POST /approvals/{approval_request_id}/approve`
- `POST /approvals/{approval_request_id}/deny`
- `GET /audit`

## Durable Model

Phase 2 adds durable PostgreSQL-oriented persistence for users, repositories, repo indexes, tasks, agent runs, agent steps, tool calls, approval requests, patch artifacts, validation runs, audit events, and policy decisions.

Tool calls persist trace fields including tool name, input summary, output summary, status, duration, approval requirement, and error text. Service-layer writes redact common secret patterns before summaries are stored.

## Local Model Gateway

Phase 3 adds a provider-agnostic gateway for local vLLM OpenAI-compatible endpoints. It supports chat completions, embeddings, streaming chat chunks, model-server health checks, timeout/retry policy, and a clearly unsupported reranking placeholder.

Model role names are configured with environment variables:
- `SWITCH_PLANNER_MODEL`
- `SWITCH_CODER_MODEL`
- `SWITCH_REVIEWER_MODEL`
- `SWITCH_SUMMARIZER_MODEL`
- `SWITCH_EMBEDDING_MODEL`
- `SWITCH_RERANKER_MODEL`

`SWITCH_LOCAL_ONLY=true` rejects non-local model endpoints.

## Code Intelligence Indexer

The local indexer combines:
- git-aware file crawling that respects `.gitignore`
- binary, vendor, generated, and secret-file filtering
- language detection by extension
- Python AST symbol extraction, JavaScript/TypeScript import/export extraction, and Tree-sitter probing where installed
- symbol/module-based chunking
- exact search through `ripgrep`
- local embedding through the model gateway embedder interface
- vector storage through an in-memory test store or Qdrant adapter
- incremental reindexing by file hash

## Retrieval Engine

The hybrid retrieval engine builds compact, auditable context bundles for coding tasks. It combines exact text, symbol, semantic vector, file path, import/export dependency, git history, and source/test-pairing lanes.

Each bundle keeps file path, line range, chunk id, symbol name when available, git commit, selected lanes, score, and human-readable reasons. Retrieval deduplicates overlapping chunks and enforces a context budget so prompts receive focused context instead of whole repositories.

## Policy Engine

The local policy engine is deny-by-default and controls read, plan, patch proposal, workspace write, sandbox command, and branch artifact operations.

Permission levels:
- Level 0: read-only Q&A
- Level 1: plan only
- Level 2: propose patch/diff
- Level 3: write to isolated workspace
- Level 4: run allowlisted commands in sandbox
- Level 5: create branch/PR artifact with approval
- Level 6: reserved/admin only, never autonomous

The engine denies shell passthrough, writes outside the workspace, secret access by default, protected branch writes, policy file modification, and branch/PR artifacts without human approval. Evaluations can persist `PolicyDecision` records and audit events.

## Tool Layer

The internal tool layer exposes typed, policy-checked tools for agent use:
- `read_file`
- `list_files`
- `search_text`
- `search_symbols`
- `retrieve_context`
- `propose_patch`
- `apply_patch_to_workspace`
- `get_git_diff`
- `run_validation_command`
- `summarize_diff`
- `request_approval`
- `create_branch_artifact`

Each tool has typed input and output schemas, runs policy checks before actions, writes a `ToolCall`, emits an `AuditEvent`, returns structured errors, and compacts large outputs for model-facing responses.

## Web Dashboard

The dashboard is a dense internal operations UI for local visibility and human approval. It
shows repository status, task state, run timelines, retrieval context, diffs, validation
results, pending approvals, audit events, and model/server health.

The dashboard does not talk to the database directly and does not run tools or shell commands.
It uses backend APIs for all reads and approval decisions.

## Evaluation Harness

Phase 15 adds a local synthetic evaluation harness for retrieval accuracy, file localization,
patch correctness, test pass rate, regression avoidance, policy compliance, secret handling,
prompt injection resistance, diff review quality, and final report truthfulness.

Run:

```bash
make eval
```

Reports are generated under `evals/reports/`. See
[evaluation harness docs](docs/development/evaluation.md).

## Documentation

- [Local coding agent architecture](docs/architecture/local_coding_agent.md)
- [Security model](docs/architecture/security_model.md)
- [Implementation phases](docs/roadmap/phases.md)
- [Local setup](docs/development/local_setup.md)
- [Evaluation harness](docs/development/evaluation.md)
