# SWITCH Phase Plan

## Phase 0 - Audit and Doctrine Lock

Goal: Document the current codebase, lock City Tele Coin operational doctrine, and identify gaps without changing runtime behavior.

Likely files/modules affected: `docs/`.

Expected outputs: overview, architecture audit, CTC operational scope, security/approval model, and phased roadmap.

Validation commands: `python -m pytest`, `python -m compileall app`, `ruff check .`, `mypy app`, `npm run lint`, `npm run typecheck`.

Risks: documenting assumptions as if implemented; overlooking unauthenticated surfaces; mixing coding-agent capabilities with operations automation.

What not to do: rewrite the app, add integrations, add automation, send communications, change production behavior, or add unrelated project references.

## Phase 1 - Core Kernel and Project Boundaries

Goal: Establish identity, RBAC, tenant/workspace boundaries, CTC doctrine checks, and deployment-safe defaults before operational ingestion.

Likely files/modules affected: `app/core`, `app/api`, `app/security`, `app/models`, `app/db`, `dashboard`, deployment docs.

Expected outputs: authenticated operator identity, role definitions, route protection, host/web surface policy, workspace/facility scoping model, and doctrine checks in prompts/docs/UI copy.

Validation commands: backend tests, API auth tests, route access tests, dashboard lint/typecheck.

Risks: treating request-supplied user IDs as identity; exposing web chat/repo surfaces without auth; enabling memory ingestion before classification.

What not to do: ingest CTC operational records, add vendor integrations, or grant broad network access.

## Phase 2 - Domain Data Model: Sites, Circuits, Vendors, Equipment

Goal: Add approved CTC domain schemas after data classification and access boundaries are documented.

Likely files/modules affected: `app/models`, `app/db/repositories.py`, Alembic migrations, schemas, docs.

Expected outputs: durable entities for sites/facilities, circuits, vendors, equipment, and scoped relationships.

Validation commands: migration tests, persistence tests, typecheck, lint.

Risks: overfitting schemas before source data is understood; storing sensitive fields without classification; missing history/versioning requirements.

What not to do: import live operational data or create fake integrations.

## Phase 3 - Evidence Store and Audit Log

Goal: Use existing courthouse and audit patterns to store evidence separately from accepted operational truth.

Likely files/modules affected: `app/courthouse`, `app/services/audit.py`, `app/models`, Alembic migrations, docs.

Expected outputs: classified evidence intake, claim/verdict workflow, canonical operational state, append-oriented audit requirements.

Validation commands: courthouse tests, audit tests, migration tests, typecheck.

Risks: persisting raw sensitive content in snapshots; treating retrieval as truth; allowing unaudited evidence changes.

What not to do: auto-promote evidence to canonical truth or expose raw sensitive evidence to tools.

## Phase 4 - Ticket Context Builder

Goal: Compile ticket-centered context packets from approved records, evidence, site/circuit/vendor history, and knowledge-base content.

Likely files/modules affected: services, schemas, API routes, courthouse context compiler, tests.

Expected outputs: structured ticket context packets with citations, warnings, exclusions, and next-action drafts.

Validation commands: unit tests for packet assembly, privacy gate tests, API tests.

Risks: leaking unrelated site data; omitting provenance; using contradicted or superseded records as facts.

What not to do: mutate ticket systems or update ticket status automatically.

## Phase 5 - Knowledge Index and Retrieval

Goal: Index approved internal knowledge and operational documentation with scoped retrieval and provenance.

Likely files/modules affected: `app/indexing`, `app/retrieval`, `app/vector`, ingestion services, docs.

Expected outputs: classified knowledge ingestion, scoped search, citation-preserving retrieval, exclusion of secrets and unapproved sources.

Validation commands: indexing tests, retrieval tests, vector tests, secret-exclusion tests.

Risks: indexing sensitive or unrelated files; cross-scope retrieval leakage; stale knowledge appearing authoritative.

What not to do: retrieve whole repositories or broad document sets into prompts.

## Phase 6 - Approval Queue and Action Policy

Goal: Make approval gates operations-grade with authenticated approvers, action classes, expiry, evidence binding, and audit.

Likely files/modules affected: `app/api/routes/approvals.py`, `app/security`, `app/services`, dashboard approval pages, models/migrations.

Expected outputs: role-aware approval queue, policy decisions for action classes, immutable approval attribution, denial reasons, and audit trails.

Validation commands: approval tests, policy tests, API auth tests, dashboard tests.

Risks: approval replay, approving mismatched artifacts, weak identity, missing expiry.

What not to do: allow approval by request-supplied identity alone.

## Phase 7 - Vendor Escalation Packet Generator

Goal: Generate draft-only vendor escalation packets from approved evidence, ticket history, circuit/vendor records, and troubleshooting steps.

Likely files/modules affected: services, schemas, API routes, dashboard, courthouse compiler, docs.

Expected outputs: escalation packet drafts with citations, missing-information warnings, risk notes, and approval status.

Validation commands: packet generation tests, privacy/export gate tests, UI tests.

Risks: producing inaccurate provider facts; exposing sensitive records; implying a draft was sent.

What not to do: send emails, submit portal updates, or contact vendors automatically.

## Phase 8 - Local Model Adapter and Prompt Safety

Goal: Harden local model usage for operational support with prompt safety, model-call ledgering, and bounded context.

Likely files/modules affected: `app/model_gateway`, chat/ask routes, prompt construction, model-call repositories, tests.

Expected outputs: uniform model-call records, local-only production policy, prompt templates for CTC operations, refusal patterns for blocked actions.

Validation commands: model gateway tests, chat route tests, prompt safety tests, typecheck.

Risks: remote model use in production; prompt injection from documents; model output treated as operational truth.

What not to do: let LLM output mutate records or trigger external actions.

## Phase 9 - Web UI / Operator Console

Goal: Provide an authenticated operator console for CTC workflows while preserving host-only diagnostics and administration.

Likely files/modules affected: `dashboard`, API schemas/routes, auth integration, docs.

Expected outputs: ticket/site/circuit/vendor views, context packet display, escalation draft review, approval queue, audit views, metrics on host dashboard.

Validation commands: dashboard lint, dashboard typecheck, route authorization tests, API tests.

Risks: exposing admin or sensitive views on the network web surface; confusing drafts with sent communications.

What not to do: add unauthenticated operational views or network automation controls.

## Phase 10 - Test, Hardening, Deployment

Goal: Harden deployment, reliability, retention, audit review, backup/restore, monitoring, and operator documentation.

Likely files/modules affected: deployment docs, Docker Compose, scripts, tests, operations docs.

Expected outputs: production checklist, backup/restore verification, audit review procedure, retention policy, disaster recovery notes, monitored service health.

Validation commands: full backend tests, frontend checks, migration smoke, compose config, evaluation suite, backup/restore drills.

Risks: weak credentials, incomplete retention policy, untested migrations, missing restore process, insufficient audit review.

What not to do: ship production use without identity/RBAC, data classification, and approval hardening.
