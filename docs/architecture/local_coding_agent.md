# Local Coding Agent Architecture

## Purpose

SWITCH is a local-first coding agent platform for employer-controlled repositories. The platform should help read, retrieve, plan, propose, validate, review, and prepare code changes while keeping policy decisions outside the model.

The model may propose. The platform decides what is allowed.

## Repository Baseline

The current repository is a Phase 1 Python backend foundation.

Observed structure:
- `.gitignore`
- `README.md`
- `AGENTS.md`
- `docker-compose.yml`
- `pyproject.toml`
- `app/`
- `tests/`
- `docs/`
- `scripts/`

Observed Python package:
- `app.main`: FastAPI app factory and ASGI app
- `app.api`: API router and route modules
- `app.core.config`: Pydantic settings loaded from environment variables
- `app.core.logging`: structured logging
- `app.schemas`: health and version response schemas
- `app.db`: SQLAlchemy base, session, and repository layer
- `app.models`: durable entities and status enums
- `app.services`: persistence services for runs, tools, and audit events
- `app.security`: redaction and policy support
- `app.model_gateway`: provider-agnostic local vLLM-compatible model gateway
- `app.indexing`: local code intelligence indexing, exact search, chunking, embeddings, and vector-store boundary
- `app.retrieval`: hybrid local retrieval engine with citations, line ranges, and context budgets
- `app.agents`, `app.tools`, `app.sandbox`: package boundaries for later phases
- `alembic`: database migration environment and versions

Observed tooling:
- Package manager/build metadata: `pyproject.toml` with Hatchling
- Runtime: Python 3.12+
- API framework: FastAPI
- Tests: pytest
- Lint/format: Ruff
- Type checking: mypy strict mode
- Local service definitions: Docker Compose
- Migrations: Alembic

The repo is not initialized as git in this workspace.

## Target Architecture

The backend should move toward this structure:

- `app/main.py`: FastAPI application factory and process entrypoint
- `app/api/`: HTTP routers, dependencies, and response mapping
- `app/core/`: settings, logging, lifecycle wiring, and application constants
- `app/db/`: database sessions, migrations, and repository implementations
- `app/models/`: database models
- `app/schemas/`: Pydantic request/response schemas
- `app/services/`: durable business services
- `app/agents/`: deterministic agent lifecycle orchestration
- `app/tools/`: audited tool interfaces and tool policies
- `app/security/`: approval, branch, secret, and network policy
- `app/indexing/`: repo indexing, retrieval, and embedding coordination
- `app/retrieval/`: ranked context retrieval over indexed local repositories
- `app/sandbox/`: Docker/Podman execution adapters
- `tests/`: unit, integration, and policy tests
- `docs/`: architecture and operator documentation
- `scripts/`: local development commands

## Core Components

### API

FastAPI exposes health, version, task/run, approval, audit, and admin endpoints. API handlers should remain thin and delegate policy-sensitive work to services.

### Local Inference

Inference is provided through a local vLLM-compatible endpoint. The platform must not assume cloud LLM credentials or hosted model APIs.

Expected contract:
- Endpoint is configured by environment variable.
- Endpoint host must be localhost or approved local network.
- Requests and responses are auditable.
- Model output is treated as untrusted proposal data.
- Model roles are configured independently for planning, coding, review, summarization, embeddings, and reranking.
- Prompt and repository content are not written to logs; gateway logs record counts, roles, lengths, and content fingerprints.

### Durable State

PostgreSQL stores:
- repositories
- indexed revisions
- tasks
- runs
- plans
- proposed patches
- validation results
- approvals
- tool calls
- audit events
- policy decisions

### Retrieval

Repo intelligence combines:
- exact text search with ripgrep
- symbol and syntax search with Tree-sitter
- semantic search with Qdrant or pgvector
- git metadata including branches, commits, changed files, authorship, and blame context

No single retrieval mode is sufficient for production agent behavior.

Current implementation:
- uses `git ls-files -co --exclude-standard` when available to respect `.gitignore`
- skips common vendor/generated directories and binary extensions
- skips secret-looking filenames and files containing obvious secret assignments
- detects language by extension
- extracts Python functions, classes, methods, imports, and exports with `ast`
- extracts JavaScript/TypeScript imports, exports, functions, and classes with conservative syntax patterns
- probes for Tree-sitter availability while retaining deterministic fallbacks
- chunks by extracted symbols plus module-level remainder
- embeds chunks through an injected local embedder
- stores vectors through a `VectorStore` protocol with in-memory and Qdrant implementations
- tracks incremental reindexing by file SHA-256
- ranks hybrid retrieval lanes across exact text, symbols, semantic vectors, file paths, imports/exports, git history, and source/test pairing
- returns context bundles with file path, chunk id, symbol name, git commit, and line-range citations
- enforces deterministic context budgets before constructing agent-facing context
- filters retrieval candidates through the indexed snapshot so ignored, binary, vendor, generated, and secret-looking files excluded by indexing are not reintroduced by exact search

### Queue and Cache

Redis supports local queues, cache, coordination locks, and transient run state. Durable history remains in PostgreSQL.

### Sandboxed Execution

Validation and build commands run inside Docker or Podman sandboxes. The sandbox layer owns command allowlists, mounted paths, network policy, resource limits, and output capture.

The application must not expose broad shell access.

### Agent Lifecycle

The lifecycle remains deterministic where possible:

1. Read repository state
2. Retrieve relevant context
3. Build a plan
4. Propose a patch
5. Run allowed validation
6. Review the diff
7. Require human approval
8. Prepare branch or PR output

Human approval is required before write, push, or PR-producing actions.

The agent lifecycle is an architectural target for later phases. It is not implemented in Phase 1.

## Phase 0 Decision Lock

Locked decisions:
- Local vLLM-compatible inference only
- No cloud LLM APIs
- PostgreSQL for durable state
- Qdrant or pgvector for vector retrieval
- Redis for local queue/cache
- Docker or Podman for sandboxed execution
- Audited tool calls
- Human approval before write/push/PR actions
- Repo indexing combines exact, symbol, semantic, and git metadata

Open choices for later phases:
- Qdrant vs pgvector as default vector store
- LangGraph vs deterministic custom workflow engine
- SQLAlchemy model layout and migration tool choice
- Final Next.js dashboard structure
