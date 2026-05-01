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

Phase 1B adds a deterministic action classifier in `app/security/action_policy.py`. The classifier maps normalized action names to the classes below. Unknown or empty action names are classified as `blocked` by default. This policy is static code, not prompt text, and LLM output must not control or override classification.

### `read_only`

Read-only actions inspect approved data and return summaries, citations, or context without changing records or contacting external systems.

Examples:

- Summarize ticket: `read_only`
- Lookup site: `read_only`
- Retrieve knowledge-base procedure: `read_only`
- Assemble site context from approved internal records: `read_only`

### `draft_only`

Draft-only actions prepare text or structured packets for human review. They do not send, apply, update, or mutate.

Examples:

- Draft email to vendor: `draft_only`
- Draft outage update: `draft_only`
- Prepare vendor escalation packet: `draft_only`
- Generate escalation packet: `draft_only`

### `requires_approval`

Actions in this class may affect external parties, operational systems, or official records. They require explicit approval by an authenticated and authorized human before execution.

Examples:

- Send email to vendor: `requires_approval`
- Submit provider portal update: `requires_approval`
- Modify ticket record: `requires_approval`
- Update ticket status from AI-prepared recommendation: `requires_approval`

### `admin_only`

Admin-only actions require elevated authorization and should generally be unavailable to normal operator workflows.

Examples:

- Delete records: `admin_only`
- Change network configuration: `admin_only`
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

## Phase 1B Baseline Classifications

The initial action map is intentionally small:

| Action name | Class |
| --- | --- |
| `summarize_ticket` | `read_only` |
| `lookup_site` | `read_only` |
| `draft_vendor_email` | `draft_only` |
| `generate_escalation_packet` | `draft_only` |
| `send_vendor_email` | `requires_approval` |
| `modify_ticket_record` | `requires_approval` |
| `change_network_config` | `admin_only` |
| `delete_records` | `admin_only` |
| `export_sensitive_data` | `blocked` |

This phase does not implement sending, ticket mutation, network changes, exports, provider portal actions, or other integrations. It only establishes a deterministic classification foundation for later approval and audit workflows.

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

Phase 1C defines a database-backed audit log interface for important SWITCH actions. Audit events include:

- `id`
- `timestamp`
- `actor`
- `action`
- `action_class`
- `target_type`
- `target_id`
- `summary`
- `metadata`
- `status`
- `correlation_id`

Allowed audit statuses are:

- `proposed`
- `drafted`
- `approved`
- `rejected`
- `executed`
- `failed`
- `blocked`

Audit metadata must not store secrets. The audit service redacts known secret-looking metadata keys and secret-looking summary text before persistence. This phase establishes the interface and query paths; it does not wire every workflow or create fake execution records.

Current audit records are application database rows. Future production hardening should add retention policy, export/review workflow, tamper-evidence, and authenticated actor binding for all high-impact actions.

## Data Export Boundaries

SWITCH should not export operational data to unapproved external services. Model calls should remain local-only in production unless a specific policy exception is approved. Retrieval and context compilation must enforce data classification, workspace scope, and least-privilege access before operational records are indexed.
