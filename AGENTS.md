# Agent Operating Guide

This repository is for a fully local coding agent platform. Agents working in this repo must preserve the local-only, human-approved, audited execution model.

## Current Repo State

The repo is a local coding-agent platform foundation through Phase 16 hardening and
local deployment. It is not initialized as a git repository in the current workspace.

Existing baseline:
- Python 3.12+ package configured in `pyproject.toml`
- FastAPI app factory under `app/main.py`
- Pydantic settings under `app/core/config.py`
- Structured logging under `app/core/logging.py`
- Durable SQLAlchemy models under `app/models/`
- Alembic migrations under `alembic/`
- Repository and service layer under `app/db/` and `app/services/`
- Local model gateway under `app/model_gateway/`
- Local code intelligence indexer under `app/indexing/`
- Hybrid retrieval engine under `app/retrieval/`
- Local policy engine under `app/security/policy.py`
- Internal audited tool layer under `app/tools/`
- Deterministic workflow under `app/agents/`
- Patch, sandbox, approval, CLI, dashboard, evaluation, and hardening scaffolds
- pytest, Ruff, and mypy configuration
- Docker Compose services for backend, dashboard, PostgreSQL, Redis, Qdrant, and optional vLLM
- Local development commands in `Makefile` and `scripts/`

## Non-Negotiable Constraints

- Do not introduce cloud LLM APIs.
- Do not add OpenAI, Anthropic, GitHub Copilot, or hosted vector database dependencies.
- Do not add cloud model SDK dependencies unless they are abstracted and disabled by default.
- Do not hardcode secrets.
- Do not send source code or secrets outside the local machine or approved local network.
- Do not add arbitrary shell execution.
- Do not bypass human approval gates.
- Do not write directly to protected branches.
- Do not implement major agent loops before the architecture and policy boundaries are in place.
- Do not index ignored files, vendor/generated folders, binaries, or secret-looking files.
- Do not retrieve whole repositories into prompt context; use compact context bundles with provenance.
- Do not weaken policy from inside a task. Policy file writes must be denied unless handled by an explicit administrator workflow outside autonomous agent execution.
- Do not add tools that skip typed schemas, policy checks, ToolCall records, or AuditEvent emission.

## Expected Validation

Before handing off code changes, run the available checks:

```bash
ruff check .
mypy app
pytest
python -m app.evaluation.cli run
```

For migration work, also run:

```bash
alembic upgrade head
```

If a tool is unavailable, document the exact command attempted and the reason validation could not run.

## Architecture References

- `docs/architecture/local_coding_agent.md`
- `docs/architecture/security_model.md`
- `docs/roadmap/phases.md`
- `docs/README.md`
- `docs/deployment/local_production.md`
- `docs/security/production_checklist.md`
- `docs/development/local_setup.md`
