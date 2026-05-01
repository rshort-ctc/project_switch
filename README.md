# SWITCH

SWITCH is a Python-based internal operations intelligence platform for support,
engineering, site, circuit, vendor, ticket, and escalation workflows.

SWITCH is employer-scoped for City Tele Coin operational work. It is intended to
help authorized staff assemble accurate context, review cited evidence, draft
safe communications, prepare troubleshooting steps, and keep an audit trail
without bypassing human judgment or approval gates.

## Product Scope

SWITCH supports controlled assistance for:

- Site, facility, circuit, vendor, and equipment context assembly.
- Ticket and outage history review.
- Troubleshooting procedure lookup and preparation.
- Vendor escalation packet drafting.
- Billing, order, and MARC/order tracking context gathering where applicable.
- Internal knowledge-base and repository context retrieval with provenance.
- Controlled AI-assisted drafting, analysis, and risk explanation.

SWITCH is not an autonomous operations system. It does not send vendor-facing
communications, change network configuration, use credentials silently, export
sensitive data, or mutate operational records without explicit policy and human
approval.

## Operating Principles

- Draft, do not send.
- Propose, do not apply.
- Prepare, do not mutate.
- Explain risk before action.
- Keep an audit trail for important actions.
- Separate raw evidence from accepted operational truth.
- Require approval gates for external-facing or system-changing work.
- Keep company data local or inside approved local network boundaries.

## Intended Users

- Support operators reviewing tickets, outages, sites, and vendor context.
- Network and telecom engineers preparing troubleshooting and escalation work.
- Escalation coordinators drafting vendor-facing packets for human review.
- Approved administrators responsible for access, policy, audit, and retention.

## Repository Status

This repository currently provides the local platform foundation for SWITCH. It
is not yet a complete City Tele Coin production domain system.

Current baseline:

- Python package: `switch-agent`
- Runtime target: Python 3.12+
- Backend framework: FastAPI
- Config: Pydantic Settings with `SWITCH_` environment variables
- Logging: stdlib structured JSON logging
- Database ORM: SQLAlchemy 2
- Migrations: Alembic
- Model gateway: local vLLM-compatible and Ollama-compatible HTTP clients
- Tests: pytest
- Lint/format: Ruff
- Type checking: mypy strict mode
- Local services: PostgreSQL, Redis, and Qdrant via Docker Compose
- Dashboard: Next.js host dashboard and limited network web surface under `dashboard/`

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
- `app/indexing/`: local repository crawler, chunker, search, embedding pipeline, and vector-store boundary
- `app/retrieval/`: hybrid retrieval engine with provenance and context budgets
- `app/courthouse/`: governed evidence, claim, verdict, canonical state, loop, and snapshot services
- `app/agents/`, `app/tools/`, `app/sandbox/`: controlled workflow, typed tool, and sandbox boundaries
- `alembic/`: database migrations
- `tests/`: configuration, logging, health, version, migration, persistence, retrieval, policy, and governance tests
- `docker-compose.yml`: API, migration, dashboard, web dashboard, PostgreSQL, Redis, Qdrant, and optional vLLM services
- `scripts/` and `Makefile`: local development and deployment commands
- `dashboard/`: internal dashboard surfaces that consume backend APIs only

## Local-Only Position

SWITCH assumes:

- Inference is provided by local or approved local-network model endpoints.
- Cloud LLM APIs are not used by default.
- Source code, prompts containing source code, secrets, repository metadata, embeddings, and audit logs remain local.
- PostgreSQL stores durable task, run, approval, audit, and governance state.
- Qdrant stores local embeddings.
- Redis is available for local queues and cache.
- Docker or Podman sandboxes execute validation and build commands.
- Human approval is required before write, push, external-facing, or system-changing actions.
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

Run the local stack with both UI surfaces:

```bash
scripts/switch start
```

The host dashboard runs in Docker at `http://127.0.0.1:55601`. The network web
surface also runs in Docker on `SWITCH_WEB_PORT` and defaults to `0.0.0.0:55602`.

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
- `POST /ask`
- `POST /chat`
- `POST /chat/code/run`
- `GET /tasks`
- `POST /tasks`
- `POST /tasks/{task_id}/run`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/logs`
- `GET /tasks/{task_id}/diff`
- `GET /tasks/{task_id}/validations`
- `GET /approvals/pending`
- `POST /approvals/{approval_request_id}/approve`
- `POST /approvals/{approval_request_id}/deny`
- `GET /audit`

## Context Retrieval

The hybrid retrieval engine builds compact, auditable context bundles. It
combines exact text, symbol, semantic vector, file path, import/export
dependency, git history, and source/test-pairing lanes.

Each bundle keeps file path, line range, chunk id, symbol name when available,
git commit, selected lanes, score, and human-readable reasons. Retrieval
deduplicates overlapping chunks and enforces a context budget so prompts receive
focused context instead of whole repositories.

Repo Q&A through `POST /ask`, `POST /chat`, and `switch ask` requires a ready
persistent repo index. Run `switch repo index <repo-id>` first. Ask/chat use
Qdrant-backed semantic retrieval filtered by repo id plus local exact search;
they do not re-index repositories per request and do not use deterministic test
embeddings in production routes.

If a local summarizer, planner, or coder model is configured, `/ask` generates
an answer through the local model gateway using only retrieved context. If no
answer model is configured or the model gateway is unavailable, the response is
explicitly marked `degraded=true` and returns context-only citations instead of
pretending a model answered.

## Policy and Approval

The local policy engine is deny-by-default and controls read, plan, patch
proposal, workspace write, sandbox command, and branch artifact operations.

Permission levels:

- Level 0: read-only Q&A
- Level 1: plan only
- Level 2: propose patch/diff
- Level 3: write to isolated workspace
- Level 4: run allowlisted commands in sandbox
- Level 5: create branch/PR artifact with approval
- Level 6: reserved/admin only, never autonomous

The engine denies shell passthrough, writes outside the workspace, secret access
by default, protected branch writes, policy file modification, and branch/PR
artifacts without human approval. Evaluations can persist `PolicyDecision`
records and audit events.

## Dashboard Surfaces

The host dashboard is a dense internal operations UI for local visibility and
human approval. It shows repository status, task state, run timelines, retrieval
context, diffs, validation results, pending approvals, audit events, and
model/server health.

The network web surface is the limited browser surface for LAN machines. It is
locked to chat and repository views; diagnostics, approval actions, audit logs,
task views, sandbox console access, and metrics stay on the host dashboard.

Neither surface talks to the database directly. Both use backend APIs for reads
and allowed mutations.

## Documentation

- [SWITCH overview](docs/switch_overview.md)
- [City Tele Coin operational scope](docs/ctc_operational_scope.md)
- [Current architecture](docs/current_architecture.md)
- [Security and approval model](docs/security_and_approval_model.md)
- [Architecture baseline](docs/architecture/local_coding_agent.md)
- [Security model](docs/architecture/security_model.md)
- [Implementation phases](docs/roadmap/phases.md)
- [Local setup](docs/development/local_setup.md)
- [Evaluation harness](docs/development/evaluation.md)
