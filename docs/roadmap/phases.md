# Implementation Roadmap

## Phase 0: Repo Recon and Architecture Lock

Status: current phase.

Outcomes:
- Repository baseline documented.
- Local-only architecture decisions recorded.
- Security model documented.
- Implementation phases defined.
- Development setup documented.

No major runtime features are introduced in this phase.

## Phase 1: Backend Foundation

Build the production-grade backend foundation.

Status: implemented in the current working tree.

Scope:
- Adopt target `app/` backend structure.
- FastAPI app with `/health`, `/health/details`, and `/version`.
- Typed environment-driven settings.
- Structured logging.
- Local-only mode configuration.
- Development scripts for install, format, lint, typecheck, test, and server.
- Test harness for API and configuration.
- Formatting, linting, and typechecking setup.

Non-goals:
- Agent brain
- arbitrary shell execution
- cloud services

## Phase 2: Durable State and Audit

Add PostgreSQL-backed persistence.

Status: implemented in the current working tree.

Scope:
- Database models for repositories, tasks, runs, approvals, tool calls, and audit events.
- Migration setup.
- Repository/service layer.
- Append-only audit event model.
- Tests for persistence and audit ordering.

## Phase 3: Local Model Gateway

Status: implemented in the current working tree.

Scope:
- Local vLLM OpenAI-compatible client.
- Provider-agnostic model registry.
- Chat completion interface.
- Embedding interface.
- Explicit reranking placeholder.
- Safe request/response logging.
- Timeout and retry policy.
- Streaming chat support.
- Local model-server health endpoint.
- `LOCAL_ONLY` enforcement for model endpoints.

## Phase 4: Repository Intelligence

Status: implemented in the current working tree as the Phase 5 code intelligence indexer request.

Scope:
- ripgrep exact search adapter.
- Tree-sitter symbol/syntax extraction.
- Git metadata ingestion.
- Local embedding pipeline through vLLM-compatible or local embedding endpoint.
- Qdrant or pgvector vector retrieval.
- Retrieval result ranking and provenance.

Implemented details:
- git-aware crawler respecting `.gitignore`
- language detection
- Python AST and JavaScript/TypeScript symbol extraction, with Tree-sitter availability probing
- exact search with ripgrep
- symbol/module chunking
- local embedding interface
- in-memory vector store for tests and Qdrant adapter for local deployment
- incremental reindexing by file hash

## Phase 5: Sandbox and Tool Registry

Add audited, policy-controlled tools.

Scope:
- Tool registry.
- Docker/Podman sandbox adapter.
- Command allowlists.
- Network and filesystem restrictions.
- Validation command execution.
- Structured tool-call audit records.

## Phase 6: Deterministic Agent Workflow

Implement the agent lifecycle without bypassing policy.

Status: retrieval engine foundation implemented in the current working tree; full agent lifecycle remains future work.

Scope:
- Read, retrieve, plan, propose patch, validate, review diff, require approval, prepare output.
- LangGraph or deterministic custom workflow engine decision.
- Run state transitions.
- Patch artifact storage.
- Policy checks at every state-changing boundary.

Implemented retrieval foundation:
- Hybrid `app.retrieval` engine over indexed local repositories.
- Retrieval lanes for exact text, symbols, semantic vectors, file paths, imports/exports, git history, and source/test pairing.
- Context bundles include provenance with file path, line range, chunk id, symbol name, lane, and git commit.
- Context budget enforcement omits bundles that would exceed the configured token budget.
- Retrieval tests use synthetic local git repositories and verify ignored and secret-looking files stay excluded.

## Phase 7: Policy and Permission Engine

Status: implemented in the current working tree.

Scope:
- Permission levels 0 through 6.
- Deny-by-default operation evaluation.
- Command allowlist.
- Path allowlist.
- Workspace-only write checks.
- Secret and policy-file write restrictions.
- Protected branch checks.
- Human approval requirement for branch/PR artifacts.
- Durable `PolicyDecision` records and audit events.
- Tests for dangerous commands, allowed validation commands, workspace boundaries, and auditing.

## Phase 8: Tool Layer

Status: implemented in the current working tree.

Scope:
- Typed schemas for internal tools.
- Policy checks before tool actions.
- Durable `ToolCall` records.
- `AuditEvent` emission for every tool invocation.
- Structured error outputs.
- Compact model-facing results with local artifacts for larger outputs.
- Tools for file reads, file listing, text search, symbol search, context retrieval, patch proposal, workspace patch application, git diff, validation commands, diff summaries, approval requests, and branch artifacts.

## Phase 9: Human Approval and Branch Output

Add write and branch preparation flows.

Scope:
- Approval APIs.
- Diff review artifacts.
- Local branch creation after approval.
- Protected branch enforcement.
- Optional local PR metadata export.

No direct protected branch writes.

## Phase 10: CLI Operator Experience

Build the first complete operator surface.

Scope:
- Typer CLI commands for repo registration, indexing, run creation, approval, validation, and branch output.
- Clear local-only status reporting.
- Audit inspection commands.

## Phase 11: Dashboard

Add the Next.js dashboard after backend flows are stable.

Scope:
- Run list and detail views.
- Diff review and approval UI.
- Audit timeline.
- Repository indexing status.
- Local service health.

## Phase 12: Hardening

Prepare for employer-grade operation.

Scope:
- Authentication and authorization.
- Role-based approvals.
- Policy configuration.
- Secret scanning.
- Backup and restore guidance.
- Load and failure testing.
- Packaging and deployment documentation.

## Phase 13: CLI Interface

Status: implemented in the current working tree.

Scope:
- HTTP-backed Typer CLI for health, models, repos, indexing, asking questions,
  tasks, logs, diffs, approvals, and validation results.
- JSON output mode for automation.
- LOCAL_ONLY API endpoint validation.

## Phase 14: Web Dashboard

Status: implemented in the current working tree.

Scope:
- Next.js internal dashboard under `dashboard/`.
- Repo, task, approval, diff, validation, audit, retrieval context, and health views.
- Backend APIs only; no direct database or policy bypass path.

## Phase 15: Evaluation Harness

Status: implemented in the current working tree.

Scope:
- Synthetic local repos/tasks for bug fix, failing test repair, refactor, docs,
  unsafe secrets, prompt injection, risky dependency changes, and ambiguity.
- Metrics for retrieval, patching, tests, policy, approvals, and final report truthfulness.
- JSON and Markdown reports under ignored `evals/reports/`.

## Phase 16: Hardening and Local Deployment

Status: implemented in the current working tree.

Scope:
- Containerized backend and dashboard.
- Hardened Docker/Podman Compose topology for backend, database, Redis, vector
  store, optional model gateway, and dashboard.
- Backup/restore scripts and operator documentation.
- Security checklist, local model guide, onboarding, and hardening validation.

## Phase 17: VS Code and Cursor Extension

Status: implemented in the current working tree.

Scope:
- VS Code-compatible extension under `extensions/vscode-switch`.
- Local backend connection, repo selection/indexing, repo questions, task creation
  from editor context, task status, retrieved file citations, diffs, and approvals.
- Backend-only policy path: no cloud APIs, no direct shell execution, no
  extension-side agent logic, and no direct patch application.
