# Security Model

## Security Goals

SWITCH is designed for repositories that must stay inside an employer-controlled environment.

Primary goals:
- Keep source code and secrets local.
- Prevent cloud LLM or hosted vector database dependency.
- Require explicit human approval before state-changing repository actions.
- Audit every tool call and policy decision.
- Restrict execution to sandboxed, allowlisted operations.
- Make model output advisory, not authoritative.

## Local-Only Assumptions

Local-only mode means:
- LLM inference uses a local vLLM-compatible endpoint.
- Vector search uses local Qdrant or local PostgreSQL with pgvector.
- Durable state is stored in local PostgreSQL.
- Queues and cache use local Redis.
- Validation runs in Docker or Podman on local infrastructure.
- No source code, secrets, prompts containing source code, embeddings, patches, or audit logs are sent to cloud services.

Configuration must default toward local operation. Any future capability that can contact a non-local network must be explicit, policy-checked, audited, and disabled by default.

The model gateway enforces this boundary through `SWITCH_LOCAL_ONLY=true`, which rejects non-local `SWITCH_VLLM_ENDPOINT` values during settings validation.

## Trust Boundaries

### Trusted

- Platform policy engine
- Approval records created by authenticated humans
- Durable audit log
- Sandboxed execution controller
- Repository metadata read through controlled adapters

### Untrusted

- Model output
- Retrieved text snippets
- Generated shell commands
- Generated patches
- Test output
- User-provided task text
- Repository contents that may include prompt injection text

## Approval Gates

Human approval is required before:
- writing changes to a working tree
- creating or updating branches
- pushing to remotes
- opening or updating pull requests
- running privileged validation
- expanding tool permissions

Approval records should include:
- actor
- timestamp
- run id
- requested action
- diff or artifact hash
- policy decision
- resulting action id

## Branch Protection

Protected branches must not be direct write targets. The default protected set includes:
- `main`
- `master`
- `release`
- `production`

Future branch policies should support repository-level configuration, glob patterns, and server-side verification before branch output is prepared.

## Tool Policy

Tool calls must be:
- defined in a registry
- scoped by capability
- validated before execution
- audited before and after execution
- denied by default when policy is ambiguous

The platform must not expose broad shell access. Shell-like behavior, when required, belongs behind specific sandboxed tools with command allowlists and resource limits.

Current tool layer:
- exposes typed input and output schemas for each internal tool
- runs policy checks before read, write, command, patch, and branch-artifact actions
- writes durable `ToolCall` records for every invocation
- emits `tool.executed` audit events
- returns structured errors instead of leaking exceptions into agent prompts
- compacts model-facing output and stores larger content as local artifacts
- runs validation commands only as allowlisted argument lists

## Permission Levels

The policy engine evaluates explicit operations against a configured permission level:
- Level 0: read-only Q&A
- Level 1: plan only
- Level 2: propose patch or diff
- Level 3: write to an isolated workspace
- Level 4: run allowlisted commands in a sandbox
- Level 5: create branch or PR artifacts after human approval
- Level 6: reserved for administrators and unavailable to autonomous agents

The engine is deny-by-default. Unknown operations, insufficient levels, shell passthrough, non-sandboxed command execution, writes outside the workspace, secret-path access, protected branch writes, and policy-file modification are denied with human-readable reasons.

Allowed command requests are structured argument lists, not shell strings. Current validation commands are allowlisted by command prefix, such as `pytest`, `ruff check`, `ruff format`, `mypy`, and `alembic upgrade`.

## Sandbox Policy

Docker or Podman sandboxes should enforce:
- read-only source mounts unless a write phase is explicitly approved
- isolated working directories
- command allowlists
- network disabled by default
- CPU, memory, process, and timeout limits
- captured stdout, stderr, exit code, and artifact metadata

## Secrets Handling

Secrets must not be sent to models, logs, vector stores, or audit message bodies.

Required controls for later phases:
- secret scanning before indexing and prompt construction
- redaction in logs and audit events
- denylist for common secret file paths
- environment variable allowlists for sandbox execution

## Audit Model

Audit records should be append-only and durable in PostgreSQL.

Audit events should cover:
- run creation
- retrieval queries
- model calls
- proposed plans
- proposed patches
- validation commands
- sandbox execution results
- policy decisions
- approval decisions
- branch and PR output preparation

Audit entries should store structured metadata and artifact hashes instead of large opaque blobs.

Model gateway request logs must not contain raw prompts, source code, or retrieved repository content. Logs may include model role, configured model name, message counts, character counts, and redacted content fingerprints.
