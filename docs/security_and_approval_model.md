# Security and Approval Model

SWITCH is an internal City Tele Coin operations platform. Its safety model is based on least privilege, human approval, scoped data access, auditability, and strict separation between evidence, drafts, and approved operational action.

## Hard Boundaries

- No personal or private data ingestion.
- No unrelated private project references in source, docs, prompts, comments, UI copy, or operational content.
- No automatic vendor-facing communication.
- No automatic network, telecom, billing, ticketing, or production system changes.
- No silent credential use.
- No unapproved external data export.
- All external-facing drafts require human review.
- All system-changing actions require explicit approval.
- Important actions require audit records.
- Secrets must stay in environment variables or an approved secret manager.
- Access should be least privilege and scoped by role, workspace, facility, and data classification.

## Action Classes

### `read_only`

Read-only actions inspect approved data and return summaries, citations, or context without changing records or contacting external systems.

Examples:

- Summarize ticket: `read_only`
- Retrieve knowledge-base procedure: `read_only`
- Assemble site context from approved internal records: `read_only`

### `draft_only`

Draft-only actions prepare text or structured packets for human review. They do not send, apply, update, or mutate.

Examples:

- Draft email to vendor: `draft_only`
- Draft outage update: `draft_only`
- Prepare vendor escalation packet: `draft_only`

### `requires_approval`

Actions in this class may affect external parties, operational systems, or official records. They require explicit approval by an authenticated and authorized human before execution.

Examples:

- Send email to vendor: `requires_approval`
- Submit provider portal update: `requires_approval`
- Change network configuration: `requires_approval`
- Update ticket status from AI-prepared recommendation: `requires_approval`

### `admin_only`

Admin-only actions require elevated authorization and should generally be unavailable to normal operator workflows.

Examples:

- Delete records: `admin_only`
- Change security policy: `admin_only`
- Modify retention settings: `admin_only`
- Grant or revoke access: `admin_only`

### `blocked`

Blocked actions are denied unless a later explicit administrative policy creates a narrow exception with audit and approval controls.

Examples:

- Export sensitive data: `blocked` unless explicitly approved by policy.
- Use secrets from source code or chat content: `blocked`.
- Send customer or vendor communications without review: `blocked`.
- Make autonomous production changes: `blocked`.

## Approval Requirements

An approval record must bind:

- Authenticated approver identity.
- Requested action.
- Scope of the action.
- Evidence and context used.
- Risk explanation.
- Decision and timestamp.
- Result or denial reason.

Approval must not rely only on a user ID supplied in a request body. Later phases must bind approval decisions to authenticated sessions, roles, and approver eligibility.

## Audit Requirements

Important actions must emit audit records. This includes data ingestion, retrieval against sensitive scopes, context compilation, draft creation, approval requests, approval decisions, attempted system-changing actions, denied actions, and administrative changes.

Current audit records are application database rows. Future production hardening should add retention policy, export/review workflow, correlation IDs, and tamper-evidence.

## Data Export Boundaries

SWITCH should not export operational data to unapproved external services. Model calls should remain local-only in production unless a specific policy exception is approved. Retrieval and context compilation must enforce data classification, workspace scope, and least-privilege access before operational records are indexed.
