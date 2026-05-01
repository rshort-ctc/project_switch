# Switch Code + Usability Review

*Reviewer: code/architecture/security audit, 2026-04-30*
*Subject: Switch — System-Wide Intelligence for Testing, Coding, and Hardening*
*Repo: `/home/rshort/Projects/SWITCH` — branch `main`*

## Executive Summary

Switch is a **well-architected, locally-grounded foundation** for a fully local
coding-agent platform. The persistence model, policy engine, sandbox, patch
service, retrieval engine, and deterministic agent workflow are all real,
non-trivial implementations with reasonable test coverage. Local-only
enforcement of the model gateway and vector store is genuine, not theatre.

But Switch as shipped today is **not a usable coding agent**. The pieces are
there; they are not wired together. Specifically:

- The `DeterministicCodingAgentWorkflow` exists and is unit-tested, but **no
  API route or CLI command ever invokes it**. Tasks created via the API enter
  state `OPEN` and sit there.
- The `/ask` endpoint re-indexes the entire repo on every request using a
  **deterministic test-stub embedder and an in-memory vector store**, ignoring
  the configured Qdrant deployment.
- The `/approvals/{id}/approve` endpoint accepts the approving user's id from
  the request body with **no authentication** — anyone with network access to
  the API can self-approve any pending action.
- The audit log is append-only by convention but **not tamper-evident** (no
  sequence numbers, no hash chain, mutable rows).
- `LOCAL_ONLY` validation covers the model and vector endpoints but **not
  `database_url` or `redis_url`**.

Switch should be treated as the *control-plane and retrieval foundation*
through Phase 16. The autonomous-coding-agent layer that the README describes
is mostly placeholder routing — `app/agents/workflow.py` is real engineering;
the API surface to drive it is missing.

---

## Current Readiness Score

| Area | Score | Notes |
|---|---:|---|
| Architecture | 4 | Coherent layering; one duplicated stub (`app/db/models/` vs `app/models/`) |
| Local-only enforcement | 3 | Model + vector enforced at config; DB/Redis URLs unchecked |
| PostgreSQL truth layer | 4 | Schema complete, migrations linear, indexes sensible |
| Qdrant vector layer | 3 | Real adapter with payload metadata; **not used by `/ask` or `/chat`** |
| Indexing | 3 | Symbol-aware Python, regex JS/TS; **nested `.gitignore` ignored**; Tree-sitter aspirational |
| Retrieval | 4 | Genuine 7-lane hybrid retrieval with provenance, dedup, budget |
| Agent workflow | 3 | Implementation is solid; **never invoked from API/CLI** |
| Tool safety | 4 | Typed schemas, policy checks, audit, output truncation — all real |
| Policy/permissions | 4 | Deny-by-default, comprehensive ops, decisions persisted |
| Patch safety | 4 | Path traversal blocked; risk classification; rollback artifacts |
| Sandbox execution | 4 | Real `--network=none`, cap-drop, read-only rootfs, no docker socket |
| Human approvals | 1 | **No caller-identity check** on approve/deny endpoints |
| API usability | 2 | Synchronous blocking handlers; no `POST /tasks/{id}/run` |
| CLI usability | 3 | Covers the basics; no `approvals list`, no chat, no task list |
| Web usability | 3 | Pages render; risk badges, diff viewer, audit work; no agent-trigger |
| Documentation | 3 | Mostly accurate; security docs aspirational vs. wired-up reality |
| Tests | 3 | Strong unit coverage, weak on injection/escape/concurrency/E2E |
| Security | 2 | Good primitives; trust boundary at approval API is broken |
| Deployment | 4 | Loopback bind, no-new-privileges, healthchecks, rotated logs |

---

## What Works Well

- **Schema design.** All 13 expected entities exist (`User`, `Repository`,
  `RepoIndex`, `Task`, `AgentRun`, `AgentStep`, `ToolCall`,
  `ApprovalRequest`, `PatchArtifact`, `ValidationRun`, `ModelCall`,
  `AuditEvent`, `PolicyDecision`) with proper FKs, cascade rules, composite
  indexes, status enums, and a shared `TimestampMixin`. See
  [app/models/entities.py](../../app/models/entities.py) and the three Alembic
  migrations under [alembic/versions/](../../alembic/versions/).
- **Policy engine is real.** `PolicyEngine.evaluate` in
  [app/security/policy.py](../../app/security/policy.py) is deny-by-default,
  rejects shell metacharacters (`;`, `&&`, `||`, `|`, `>`, `<`, `$(`, `` ` ``),
  enforces minimum permission levels per operation, blocks writes to secret
  paths and the policy directory itself, and persists `PolicyDecision` records.
- **Sandbox is correctly hardened.** The actual `docker run` invocation in
  [app/sandbox/runner.py:137-169](../../app/sandbox/runner.py) uses
  `--network=none` by default, `--cap-drop=ALL`, `--security-opt
  no-new-privileges`, `--read-only`, `--pids-limit 256`, `--memory`, `--cpus`,
  `--tmpfs /tmp:rw,noexec,nosuid`, and **no Docker socket mount**. Workspace
  may be mounted read-only via `spec.read_only_workspace`.
- **Patch service is conservative.** `_validate_relative_path` rejects
  absolute paths and `..` parts and resolves the result back into the
  workspace. High-risk file detection (auth, migrations, deps, CI, secrets,
  policy, lockfiles, large deletions) flips `approval_required=True`. Patches
  are persisted as artifacts with a SHA-256 digest.
  [app/patches/service.py](../../app/patches/service.py).
- **Hybrid retrieval is genuinely hybrid.** All seven lanes — exact
  (ripgrep), symbol, semantic vector, file path, import-dependency,
  git-history, source/test pairing — are implemented end-to-end with
  per-bundle provenance (file_path, line range, chunk_id, symbol, lane,
  score, reasons), dedup, and a context-budget cap.
  [app/retrieval/engine.py](../../app/retrieval/engine.py).
- **Model gateway is local-OpenAI-compatible.** Streaming, embeddings, chat,
  health, retry/backoff, secret redaction in logs.
  [app/model_gateway/client.py](../../app/model_gateway/client.py).
- **Deterministic agent workflow with bounded retries.**
  [app/agents/workflow.py](../../app/agents/workflow.py) implements all 13
  expected states, caps `max_patch_attempts` at 3, and breaks on repeated
  failure signatures (`REPEATED_FAILURE`).
- **Sane Compose deployment.** Loopback binds, healthchecks, dependency
  ordering through a one-shot `migrate` job, log rotation, vLLM under
  `profiles: ["model"]` so it doesn't run unless asked.
  [docker-compose.yml](../../docker-compose.yml).
- **Dashboard architecture.** `dashboard/lib/api.ts` opens with
  `import "server-only";` — the dashboard cannot make DB calls or run tools;
  it is strictly a backend-API client.

---

## Critical Findings

### C1. Agent workflow is never invoked from any external surface

- **Severity:** Critical
- **Location:**
  [app/agents/workflow.py:134](../../app/agents/workflow.py#L134),
  [app/api/routes/agent.py](../../app/api/routes/agent.py),
  [app/api/routes/tasks.py](../../app/api/routes/tasks.py),
  [app/cli.py](../../app/cli.py)
- **What is wrong:** `DeterministicCodingAgentWorkflow` is a real,
  unit-tested implementation
  ([tests/test_agent_workflow.py](../../tests/test_agent_workflow.py)). But a
  search across `app/api/`, `app/cli.py`, and the dashboard finds **zero
  callers**. `/agent/models` returns role names. `POST /tasks` creates a
  `Task` and an `AgentRun` row but never calls `workflow.run()`. The only
  mutating route is `POST /tasks/{id}/apply-approved-patch`, which expects
  the caller to supply an already-formed unified diff.
- **Why it matters:** Switch's whole pitch — "engineers create a task, the
  agent plans, retrieves, patches, validates, asks for approval" — is not
  reachable. From a user's perspective, tasks are inert rows.
- **Fix:** Add a `POST /tasks/{task_id}/run` (or extend `POST /tasks`) that
  enqueues a workflow execution for that task — initially synchronous behind
  a feature flag, eventually backed by the existing Redis service via a
  worker process. Connect the workflow's `request_approval` tool output back
  to `ApprovalRequest` rows so the dashboard's pending-approvals queue
  populates from real activity.

### C2. Approval endpoints accept the deciding user from the request body without auth

- **Severity:** Critical
- **Location:** [app/api/routes/approvals.py:34-82](../../app/api/routes/approvals.py),
  schema in [app/schemas/durable.py](../../app/schemas/durable.py)
  (`ApprovalDecisionRequest`)
- **What is wrong:** `POST /approvals/{id}/approve` and `/deny` take
  `decided_by_user_id` straight from the JSON body. There is no
  authentication, no session, no header check. Any caller on the network
  can `curl` an approval to APPROVED while claiming to be any user that
  exists in `users`.
- **Why it matters:** This is the **single human gate** that the entire
  security model depends on. The README, AGENTS.md, and every doc say "the
  agent cannot push, merge, deploy, or apply changes without explicit human
  approval." That guarantee is forgeable today.
- **Fix (short-term):** Until real auth lands, require a shared header
  (`X-Switch-Approver-Token`) that the dashboard/CLI send, validated against
  a per-user token table. Reject decisions where the body's
  `decided_by_user_id` does not match the token's owner. Document
  loopback-only deployment as a hard requirement.
- **Fix (medium-term):** Introduce a real auth layer — local OIDC against the
  company IdP, or signed approver tokens issued by an admin CLI. The agent's
  own session token must be unable to approve.

### C3. `/ask` and `/chat` ignore the configured Qdrant deployment

- **Severity:** Critical (correctness/architecture)
- **Location:** [app/api/routes/ask.py:34-37](../../app/api/routes/ask.py),
  [app/api/routes/chat.py](../../app/api/routes/chat.py)
- **What is wrong:** Both routes construct
  `RepoIndexer(embedder=DeterministicEmbedder(), vector_store=InMemoryVectorStore())`
  on every request and **re-index the whole repo from scratch in the request
  thread**. `DeterministicEmbedder` is a 3-dimensional test stub
  ([app/indexing/embeddings.py:22-31](../../app/indexing/embeddings.py)) that
  hashes string length, char sum, and newline count.
  - `app/vector/qdrant.py` exists, has a real client and payload schema, and
    is never reached from any HTTP path.
  - `/ask` then returns a hard-coded answer string —
    `f"Found {len(contexts)} relevant context bundle(s) for the question."`
- **Why it matters:** The "Qdrant as vector intelligence" architectural
  pillar is configured, documented, and unused. Every public-facing question
  re-indexes the repo, blows the request budget on large repos, and uses an
  embedder that has zero retrieval quality. The persisted `RepoIndex` rows
  and the indexer service produce results that the user-facing endpoints do
  not consult.
- **Fix:** Wire `/ask` and `/chat` through `PersistentRepoIndexer` +
  `QdrantCodeChunkStore` + `LocalModelEmbedder` (the gateway-backed embedder
  in [app/indexing/embeddings.py:7-19](../../app/indexing/embeddings.py)).
  Treat indexing as a separate operation triggered explicitly by
  `POST /repos/{id}/index`, and have query routes assume the index is ready.
  Replace the hard-coded answer in `/ask` with a model-completion call (or
  drop the answer field and return only contexts).

### C4. Audit log is append-only by convention only

- **Severity:** Critical
- **Location:**
  [app/services/audit.py](../../app/services/audit.py),
  [app/models/entities.py:316-329](../../app/models/entities.py)
- **What is wrong:** `AuditEvent` has an `updated_at` column with `onupdate`
  set, no sequence/version/hash field, no DB-level immutability constraint,
  and `AuditService.record()` is callable from any service holding a
  session. An autonomous workflow could write `AuditEvent("approval.granted")`
  rows that never went through the approvals API.
- **Why it matters:** The whole "audited" claim depends on this table being
  trustworthy in a forensic sense. As shipped, an attacker (or a buggy/
  jailbroken agent) with DB access can backfill or rewrite history.
- **Fix:** Add a monotonic `sequence_num` and `prev_hash`/`event_hash` chain
  computed on insert; enforce append-only with a trigger or
  `CHECK (created_at = updated_at)`. Restrict who may call
  `AuditService.record` (e.g., a privileged session role) and make sure tool
  runtime, policy engine, and approvals service all go through the same
  emitter rather than ad-hoc inserts.

### C5. Tool stdout/stderr is persisted without secret redaction

- **Severity:** Critical
- **Location:**
  [app/tools/registry.py](../../app/tools/registry.py) (the
  `run_validation_command` and `get_git_diff` paths) and
  [app/services/tools.py](../../app/services/tools.py)
- **What is wrong:** `redact_secrets()` is applied to summaries written by
  `ToolCallService.record_tool_call` and to `PolicyEngine` reasons, but the
  raw stdout/stderr from sandboxed validation commands and the raw output
  of `get_git_diff` flow into `ValidationRun.output_summary` and
  `PatchArtifact.diff_summary` un-redacted. A failing test that prints an
  env variable, or a diff that contains a `.env` change, gets stored
  verbatim in Postgres and shown in the dashboard.
- **Why it matters:** Switch deliberately blocks indexing of `.env*`,
  `*.pem`, etc. — but allows secrets to land in the audit-visible diff and
  validation logs. Defeats the redaction layer in practice.
- **Fix:** Run `redact_secrets()` on validation stdout/stderr and on the
  diff body before persistence. Add tests that include synthetic AWS keys,
  GitHub PATs, and `Authorization: Bearer ...` lines in fixture diffs and
  test output.

---

## High Priority Findings

### H1. `LOCAL_ONLY` does not validate `database_url` or `redis_url`

- **Severity:** High
- **Location:** [app/core/config.py:165-193](../../app/core/config.py)
- **What is wrong:** The post-init `model_validator` only checks
  `vector_store_url` and `vllm_endpoint` against
  `endpoint_is_local()`. `database_url` and `redis_url` are unchecked, so a
  misconfigured `SWITCH_DATABASE_URL=postgresql://user:pass@public-host/db`
  satisfies `LOCAL_ONLY=true` and quietly ships data offsite.
- **Fix:** Extend the validator to parse Postgres and Redis URLs and apply
  the same allowed-hosts/CIDRs check. Add tests in
  `tests/test_config.py`.

### H2. Synchronous, blocking request handlers for long operations

- **Severity:** High
- **Location:**
  [app/api/routes/repos.py](../../app/api/routes/repos.py),
  [app/api/routes/ask.py](../../app/api/routes/ask.py),
  [app/api/routes/chat.py](../../app/api/routes/chat.py),
  [app/api/routes/tasks.py](../../app/api/routes/tasks.py)
- **What is wrong:** Every route is `def`, not `async def`. Indexing,
  retrieval, model inference, and `git diff` execute inline. A 50k-file
  repo blocks a uvicorn worker for the duration of indexing. There is no
  job-id pattern, no Redis-backed queue use, no progress updates.
- **Fix:** Make repo indexing and agent workflow execution background jobs
  (Redis is already deployed; even an in-process `BackgroundTasks` would be
  a step up). Return `202 Accepted` with a job id; poll job status.

### H3. Approval-decision race; no row locking

- **Severity:** High
- **Location:**
  [app/api/routes/approvals.py:62-82](../../app/api/routes/approvals.py),
  [app/services/runs.py](../../app/services/runs.py)
- **What is wrong:** Two concurrent decisions on the same `ApprovalRequest`
  can both read PENDING and both write a final state. Last writer wins,
  audit shows both. No `SELECT ... FOR UPDATE` and no version column.
- **Fix:** Lock the row in `decide_approval`, or add a
  `version` integer with optimistic concurrency.

### H4. Symlink traversal not explicitly blocked in patch apply

- **Severity:** High
- **Location:**
  [app/patches/service.py:323-333](../../app/patches/service.py)
- **What is wrong:** `_validate_relative_path` calls `Path.resolve()`, which
  follows symlinks. If a prior step landed a symlink in the workspace
  (e.g., via a permitted patch), a later patch can write through it. There
  is no `O_NOFOLLOW`-equivalent check at write time and no test for this
  attack.
- **Fix:** After resolving, walk the path component-by-component and reject
  any component that is a symlink whose target leaves the workspace; or use
  `os.open(..., O_NOFOLLOW)` on each segment. Add an explicit test.

### H5. Approval requests are never created by any production code path

- **Severity:** High
- **Location:** workflow + API integration
- **What is wrong:** The `request_approval` tool exists in
  [app/tools/registry.py:596](../../app/tools/registry.py) and the workflow
  references it, but because the workflow itself is not run from any
  external surface (C1), no `ApprovalRequest` rows are ever produced. The
  dashboard's "Pending Approvals" view is permanently empty in practice.
- **Fix:** Falls out of C1.

### H6. Embedding model identity is not stored on vectors

- **Severity:** High
- **Location:** [app/vector/schemas.py](../../app/vector/schemas.py),
  [app/indexing/vector_store.py](../../app/indexing/vector_store.py)
- **What is wrong:** Payloads include `chunk_hash` and `commit_sha` but no
  `embedding_model` / `embedding_model_version`. Swap the embedding model
  and you silently mix vectors from two models in one collection.
- **Fix:** Add `embedding_model` to `CodeChunkPayload` and to the collection
  metadata. On startup, refuse to query a collection whose embedding-model
  payload disagrees with the configured model, with a clear "reindex
  required" error.

### H7. Nested `.gitignore` files are not honored

- **Severity:** High (correctness for real repos)
- **Location:**
  [app/indexing/crawler.py:103-123](../../app/indexing/crawler.py)
- **What is wrong:** Only the root `.gitignore` is parsed when not in a git
  repo (and even with git, the fallback path is a non-trivial code path).
  Real repos rely on nested ignores.
- **Fix:** When `git ls-files -co --exclude-standard` is unavailable, walk
  directories and aggregate ignore patterns as `pathspec` does. Otherwise
  document that a non-git directory may include unintended files.

### H8. Tree-sitter is referenced but not actually used

- **Severity:** High (truth-in-advertising; affects retrieval quality)
- **Location:** [app/indexing/symbols.py:30-35](../../app/indexing/symbols.py),
  [README.md](../../README.md), `docs/architecture/local_coding_agent.md`
- **What is wrong:** `_probe_tree_sitter` imports `tree_sitter` and
  discards the result. Symbol extraction is Python AST + regex for JS/TS,
  with regex for "12+ other languages" producing low-quality chunks (e.g.,
  JS function `end_line == start_line`).
- **Fix:** Either implement Tree-sitter properly with grammars vendored for
  the supported languages, or remove the claim and downgrade to "Python
  symbol-aware, others line-window."

---

## Medium Priority Findings

### M1. Two redundant model packages

- **Location:** [app/db/models/__init__.py](../../app/db/models/__init__.py),
  [app/models/__init__.py](../../app/models/__init__.py)
- Both re-export the same entities; `entities.py` is the real source. Pick
  one (`app/models/`) and delete the other to avoid future drift.

### M2. `app/core/settings.py` is a passthrough to `app/core/config.py`

- **Location:** [app/core/settings.py](../../app/core/settings.py)
- Confusing for new contributors. Remove the alias and update imports.

### M3. `ModelCall.status` is a free string

- **Location:** [app/models/entities.py:289-313](../../app/models/entities.py)
- Inconsistent with every other status column on the same model. Convert to
  enum.

### M4. Chat / ask routes do not record `ModelCall` rows

- **Location:** [app/api/routes/chat.py](../../app/api/routes/chat.py)
- The `ModelCall` table is wired only through the (unused) workflow path.
  User-initiated chat goes unrecorded at the model-call grain, leaving an
  audit gap visible in the docs but not the data.

### M5. JS/TS symbol end-lines are wrong

- **Location:** [app/indexing/symbols.py:133-147](../../app/indexing/symbols.py)
- All JS/TS symbol chunks span a single line. Hurts retrieval precision but
  doesn't break correctness.

### M6. No Qdrant rebuild-from-Postgres procedure

- If the vector volume is wiped, the only recovery is a full repo re-index.
  Acceptable, but should be a documented runbook step rather than implicit.

### M7. Approval expiry / TTL not modeled

- A pending approval lives forever. For long-running production deployments,
  add a TTL and an automatic CANCELLED transition with audit.

### M8. Default Postgres credentials in compose

- `POSTGRES_PASSWORD: ${SWITCH_POSTGRES_PASSWORD:-switch}` falls back to
  `switch`. The `.env.example` has `change-me-local-only`. If the operator
  forgets to copy `.env.example` to `.env`, the DB ships with a known
  password. Either remove the fallback or document loudly.

### M9. CLI lacks an approvals queue command

- `switch approve <id>` requires you to already know the id. There is no
  `switch approvals pending`. Today the only way to discover the id is the
  dashboard or a raw API call.

### M10. Dashboard shows degraded model fallback silently

- `/chat` falls back to retrieval-only when the model gateway is
  unreachable, returning `degraded=true, used_model=false`. The dashboard
  does not surface that flag prominently. Users may believe they are
  talking to the model.

---

## Low Priority Findings

### L1. README lists endpoints that don't exist

- README claims `GET /agent/models` (exists), but omits
  `POST /tasks/{id}/apply-approved-patch`, `POST /chat`, and
  `GET /approvals/{id}` which do exist.

### L2. `alembic/env.py:16` uses `_ = entities` to silence lint

- A more honest pattern is an `__all__`-based import for ORM metadata
  loading.

### L3. Redaction misses common patterns

- AWS Secret Access Keys (`[A-Za-z0-9/+=]{40}`), GCP service-account JSONs,
  Azure connection strings, and JWT (`eyJ...\.eyJ...\..*`) are not in
  `app/security/redaction.py`. Worth adding even though some are
  high-false-positive.

### L4. PEM redaction only catches the header

- The body of a private key is left intact unless other patterns trigger.

### L5. Migrations have no downgrade tests

- `tests/test_migrations.py` upgrades only. Even one downgrade-then-upgrade
  test would catch a category of mistakes.

---

## Usability Findings

The first five minutes for a new developer:

1. `docker compose up --build` works. Healthchecks pass. Dashboard renders.
2. `switch repo add <path>` succeeds. `switch repo index <id>` succeeds.
3. `switch ask <id> "where is auth handled"` returns retrieval bundles and a
   stub answer string — the user thinks "this is just retrieval, not an
   answer."
4. `switch task create ...` returns a task id and an agent run id.
5. `switch task status <id>` shows the run sitting at `PENDING` forever.
   Nothing happens. **This is the moment the product feels broken.**
6. The user finds the dashboard's "Pending Approvals" page; it is empty.
7. The user reads the docs, learns the agent loop is "Phase 14," gives up.

The most useful current capability is **hybrid retrieval against an indexed
repo** — the retrieval engine is genuinely good and produces faithful
provenance. The biggest missing usability feature is **a single button or
command that runs a task end-to-end**.

Support-engineer experience: the dashboard's audit log, risk badges, and
diff viewer are competent. They will become useful the moment C1 is fixed.

---

## Security Findings

| Severity | Finding | Reference |
|---|---|---|
| Critical | No auth on approval endpoints | C2 |
| Critical | Audit log not tamper-evident | C4 |
| Critical | Secrets persisted in tool output | C5 |
| High | LOCAL_ONLY skips DB/Redis URLs | H1 |
| High | Approval decision race | H3 |
| High | Symlink traversal in patch apply | H4 |
| Medium | Default DB password fallback | M8 |
| Medium | No prompt-injection tests for repo content | (gap) |
| Medium | No sandbox-escape negative tests | (gap) |
| Low | Redaction patterns incomplete | L3, L4 |

The local-only posture is largely correct: no cloud SDKs imported, no public
URLs accepted by the gateway, no Docker socket exposure, network disabled in
sandboxes. The dangerous trust boundary is the approval API, not the model
boundary.

---

## Architecture Gaps

- **Indexing pipeline split-brain.** `app/indexing/vector_store.py` and
  `app/vector/qdrant.py` both exist; the persistent path uses Qdrant, but
  the public query path uses an in-memory store. There is no single
  diagram or code path that says "this is the canonical query stack."
- **Worker/queue layer is described, not built.** Redis is in compose,
  documented as the queue/cache, but there is no worker process and no
  `app/worker/`. All work happens in the API process.
- **Agent ↔ approval ↔ patch loop is not closed.** The workflow can call
  the `request_approval` tool, but no router consumes the resulting
  `ApprovalRequest` and resumes the workflow. Approval is a one-way write
  today.
- **`Phase 16 hardening` mentioned in AGENTS.md is not visible in the
  code.** No rate limiting, no per-user quotas, no admin-only endpoints
  separated from regular endpoints.

---

## Test Coverage Gaps

The most dangerous untested areas, in order:

1. **End-to-end task execution.** No test exercises
   `POST /tasks` → workflow → patch → validation → approval → apply. The
   workflow has unit tests in isolation; nothing wires them together.
2. **Prompt injection from repo content.** No fixture file contains
   adversarial instructions to verify the agent ignores them.
3. **Sandbox escape attempts.** No test attempts `--privileged`, mounts,
   network resurrection, or fork bombs to confirm the limits hold.
4. **Patch symlink traversal.** No test creates a symlink and writes
   through it.
5. **Approval auth.** No test verifies that an unauthenticated caller can
   or cannot decide an approval.
6. **Concurrent approvals/tool-calls.** No race tests.
7. **Audit immutability.** No test attempts to update an existing
   `AuditEvent` row.
8. **Migration downgrade.** Only upgrade is tested.
9. **Nested `.gitignore`.** No test repo with nested ignores.
10. **Embedding-model swap.** No test that mismatched embeddings are
    detected.

---

## Documentation Gaps

- `docs/architecture/security_model.md` describes guarantees that the code
  does not yet enforce (notably authenticated approvals). It should mark
  these clearly as roadmap items rather than current behavior.
- `docs/architecture/storage.md` should call out that `/ask` and `/chat`
  currently bypass Qdrant.
- `docs/development/local_setup.md` should mention `alembic upgrade head`
  must run before the API starts (the compose file does this; the doc
  doesn't say so).
- The Phase 14 (autonomous agent) gap should be on the README's first page
  in a "Current Status" callout, not in `roadmap/phases.md`.
- `docs/security/production_checklist.md` should include "rotate the
  default Postgres password" and "verify approval auth" as required boxes.

---

## Recommended Remediation Plan

### Immediate Fixes

These should land before any feature work continues, in roughly this order:

1. **Wire the workflow to the API (C1, H5).** Add
   `POST /tasks/{task_id}/run` that drives `DeterministicCodingAgentWorkflow`
   in a background task. Surface produced `ApprovalRequest` rows. This
   single change converts Switch from "scaffolding" to "minimum viable
   agent."
2. **Authenticate approvals (C2).** Even a shared-token scheme is enough for
   v1. Reject decisions whose claimed user does not match the token's
   identity. Add a test.
3. **Stop bypassing Qdrant in `/ask` and `/chat` (C3).** Replace the
   in-request `RepoIndexer(InMemoryVectorStore)` with the persistent path.
   Drop `DeterministicEmbedder` in production, keep it in tests.
4. **Redact tool stdout/stderr and patch diffs before persistence (C5).**
   Add fixtures with synthetic secrets.
5. **Validate `database_url` and `redis_url` in `LOCAL_ONLY` mode (H1).**
6. **Make the audit log tamper-evident (C4).** Add a `sequence_num` and
   hash-chain column with a DB trigger. Centralize emission so no service
   can write without going through the emitter.

### Next Phase

7. **Background job runner.** Move repo indexing and workflow execution off
   the request thread; introduce a Redis-backed worker. Solves H2 and the
   blocking-handler class of issues.
8. **Symlink-safe patch apply (H4).** Component-wise check or
   `O_NOFOLLOW`.
9. **Approval row locking (H3).**
10. **Embedding-model identity stamping (H6) + nested `.gitignore` (H7).**
11. **Decide Tree-sitter (H8): implement properly or remove claim.**
12. **Add the missing CLI commands** (`approvals pending`, `task list`,
    `chat`).
13. **Surface model degradation in the dashboard (M10).**

### Later Hardening

14. **Real auth.** Local OIDC, signed approver tokens, or both.
15. **Per-user quotas / rate limits / admin endpoints.**
16. **Approval TTLs** (M7).
17. **Negative-test suite:** prompt injection, sandbox escape, symlink
    traversal, malformed tool args, oversized output, model-gateway
    timeout.
18. **Migration downgrade tests, redaction pattern expansion (L3).**
19. **Operations docs and runbooks for Qdrant rebuild and audit
    retention.**
20. **Productionize the vLLM container** (currently template-only per
    `local_production.md`).

---

## Suggested Next Prompt

```text
You are working in the Switch repository. The review at
docs/reviews/switch_review_2026-04-30.md identifies five Critical findings
(C1–C5) that block Switch from being a usable agent. Address them in a
single coordinated change, in this order, with tests at each step. Do not
add cloud dependencies. Do not weaken existing policy or sandbox controls.
Preserve mypy strict mode and ruff.

1. (C1) Wire the deterministic agent workflow to the API.
   - Add POST /tasks/{task_id}/run that:
     a. Loads the task and its latest AgentRun (or creates one).
     b. Builds a DeterministicCodingAgentWorkflow with a real ToolRegistry
        bound to that run, the configured policy engine, sandbox runner,
        patch service, retrieval engine, and model gateway.
     c. Executes workflow.run(WorkflowInput(task=task.description)) inside
        a FastAPI BackgroundTasks task. Return 202 with the run id.
     d. Persist all ApprovalRequest rows produced by the workflow's
        request_approval tool so they appear in /approvals/pending.
   - Add a CLI command `switch task run <task-id>` that calls it.
   - Add an integration test that creates a task, runs it, and asserts at
     least one AgentStep, one ToolCall, and one AuditEvent row exist.

2. (C2) Authenticate approval decisions.
   - Add a `users.approver_token_hash` column (Alembic migration) and a
     simple admin CLI `switch admin issue-approver-token --user <id>`.
     Store only a salted hash.
   - Require an `X-Switch-Approver-Token` header on
     /approvals/{id}/approve and /deny. Reject if the token does not hash
     to the user identified by `decided_by_user_id`.
   - Add tests: missing token, wrong token, mismatched user, success.

3. (C3) Make /ask and /chat use the persistent Qdrant-backed indexer.
   - Replace the in-route RepoIndexer(InMemoryVectorStore) construction
     with PersistentRepoIndexer + QdrantCodeChunkStore +
     LocalModelEmbedder.
   - If the repo's RepoIndex.status is not READY, return 409 with a
     message telling the caller to run POST /repos/{id}/index first.
   - Drop the hard-coded "Found N relevant context bundle(s)" answer from
     /ask; either return contexts only, or call the model gateway for a
     real answer when the planner model is configured.
   - Add a test that /ask without a prior index returns 409, and that
     after indexing it returns Qdrant-backed bundles.

4. (C5) Redact tool output and diffs before persistence.
   - In ToolRuntime, run redact_secrets() over stdout, stderr, diff bodies,
     and validation output before they reach ToolCallService,
     ValidationRun, or PatchArtifact. Keep raw output in artifact files
     under .switch/ but redact what reaches the database and the model
     context.
   - Extend redaction.py with AWS secret access keys, GCP service-account
     JSON markers, and JWT patterns.
   - Add fixture-based tests with synthetic secrets in test output and
     diffs; assert they do not appear in DB columns or audit summaries.

5. (C4) Make the audit log tamper-evident.
   - Add `sequence_num BIGINT` (monotonic per-table) and `event_hash`,
     `prev_hash` columns to audit_events. Compute event_hash =
     SHA-256(prev_hash || canonical_json(event_fields)) on insert.
   - Add a Postgres trigger preventing UPDATE/DELETE on audit_events.
   - Centralize all writes through AuditService.record(); audit any code
     paths that bypass it.
   - Add a test that creating events produces a verifiable chain and that
     UPDATE on the table fails.

Validation, in order:
  ruff check .
  mypy app
  alembic upgrade head
  pytest
  python -m app.evaluation.cli run

If any check fails, fix it before moving on. Update README.md and
docs/architecture/security_model.md to reflect the new behaviour. Do not
mark a critical finding "fixed" in the review file unless its tests pass.
```
