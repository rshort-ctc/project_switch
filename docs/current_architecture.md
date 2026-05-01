# Current Architecture

This document captures the current SWITCH codebase as of Phase 0. The current implementation is a local coding-agent platform foundation with strong policy, audit, retrieval, and dashboard scaffolding. It is not yet a City Tele Coin operations domain platform.

## Module Map

- `app/main.py` creates the FastAPI application.
- `app/api/` contains API routers for health, version, repositories, ask/chat, model gateway, tasks, approvals, audit, and memory.
- `app/cli.py` exposes the Typer CLI through the `switch` entrypoint.
- `app/mcp_server.py` exposes a local stdio MCP adapter for governed memory tools through the `switch-mcp` entrypoint.
- `app/core/` contains settings and logging.
- `app/models/`, `app/db/`, and `alembic/` define durable SQLAlchemy models and migrations.
- `app/indexing/`, `app/retrieval/`, and `app/vector/` provide local code indexing, hybrid retrieval, and Qdrant integration.
- `app/model_gateway/` manages local model catalog and chat-completion calls.
- `app/security/`, `app/tools/`, `app/sandbox/`, and `app/agents/` implement policy checks, typed tools, sandboxed validation, and workflow execution.
- `app/courthouse/` provides governed memory primitives: evidence, claims, verdicts, canonical state, open loops, context snapshots, and privacy/exposure gates.
- `dashboard/` contains the Next.js operator dashboard surfaces and optional Tauri desktop shell.
- `extensions/vscode-switch/` contains an editor extension surface.

## Runtime Stack

- Python 3.12+
- FastAPI and Uvicorn
- Typer CLI
- SQLAlchemy and Alembic
- PostgreSQL in Docker Compose, with SQLite used in tests and migration smoke checks
- Qdrant vector database
- Redis service provisioned in Docker Compose
- Local vLLM-compatible and Ollama-compatible model endpoints
- Pydantic Settings for environment-driven configuration
- pytest, Ruff, and mypy
- Next.js dashboard with TypeScript
- Tauri desktop shell
- Docker Compose services for API, migration, host dashboard, web dashboard, Postgres, Redis, Qdrant, and optional vLLM

## Current Data Flow

Repository workflows start with repository registration, local path validation, indexing, and Qdrant collection updates. Ask/chat workflows retrieve bounded context from indexed sources, construct prompts, call a configured local model when available, and return cited context or degraded retrieval-only responses.

Task workflows create durable tasks and agent runs, record steps, execute typed tools through policy checks, request approvals where needed, store patch and validation artifacts, and emit audit events.

Courthouse memory stores evidence and extracted claims separately from verdicts and canonical state. Context compilation enforces workspace scope, supersession rules, contradiction warnings, privacy gates, exposure gates, and snapshot records.

## Current AI and Model Flow

Model configuration is local-first. Settings default to local endpoints and `local_only=true`. Cloud-like model use is disabled by default but configurable. Repository Q&A records model-call metadata when generation is attempted. Direct non-repository chat currently records audit summary events but is not uniformly represented in the durable model-call ledger.

Prompt construction is centered on system instructions, retrieved repository context, and optional governed memory context. LLM output is advisory and should not mutate company records or external systems without explicit approval flows.

## Current Persistence Flow

Durable entities include users, repositories, repo indexes, tasks, agent runs, steps, tool calls, approvals, patches, validation runs, model calls, audit events, policy decisions, and courthouse memory tables.

Migrations are linear through the current Alembic head. Tests create in-memory SQLite schemas from SQLAlchemy metadata.

## Current API, CLI, and UI Flow

The API surface includes health/version, repository registration/indexing/status, ask/chat, sandboxed chat code execution, task run/status/log/diff/validation routes, approval decisions, audit listing, model gateway metadata, and memory routes.

The CLI mirrors core backend operations for agent health, model roles, repositories, ask, tasks, approvals, validation, and governed memory context.

The MCP surface is stdio-only and memory-focused. It adapts courthouse service calls for context compilation, docket listing, verdict explanation, canonical state, open loops, context diff, memory health, evidence submission, and candidate claim proposal. It does not expose network automation, email sending, arbitrary shell execution, or direct model mutation paths.

The dashboard has a host-oriented surface for operations and a web surface that is currently restricted to chat and repository pages. The network web surface must not be treated as a trusted administration plane until authentication and authorization are implemented.

## Known Issues and Gaps

- No City Tele Coin domain tables or workflows exist yet for sites, facilities, circuits, vendors, equipment, tickets, outages, orders, billing, or escalations.
- No production-grade authentication or role-based authorization is visible on API routes.
- Approval identity is request-supplied and not strongly bound to an authenticated operator.
- The network web surface can expose chat and repository views without authentication.
- Audit events are summary records in the application database, not tamper-evident append-only records.
- Direct non-repository chat model calls are not uniformly ledgered as durable model-call rows.
- Courthouse evidence and context snapshots can persist sensitive raw content if enabled before operational data classification is complete.
- Background workflow execution uses application background tasks; durable worker ownership is not yet a complete operations-grade job system.

## Architecture Risks

- City Tele Coin data classification and authorization must precede broad indexing or memory ingestion.
- Retrieval must become tenant, workspace, facility, and role scoped before operational records are indexed.
- External/vendor-facing actions must remain draft-only or approval-gated.
- Network/system changes must remain blocked or approval-gated and admin controlled.
- Sandbox/code execution is useful for development workflows but should not become an operations automation path without explicit policy, isolation, and approval design.
