# Switch Storage Architecture

Switch uses PostgreSQL, Qdrant, Redis, and local filesystem storage together. They
are not interchangeable.

PostgreSQL is truth. It stores canonical system state: users, repositories,
repo index status, tasks, agent runs, agent steps, model call metadata, tool
calls, approvals, policy decisions, patch metadata, validation runs, audit
events, workflow state, system configuration records, and security events. If a
record matters for auditability, authorization, task history, or compliance, it
belongs in PostgreSQL.

Qdrant is intelligence. It stores rebuildable vectors and compact payloads for
semantic retrieval: code chunks, documentation chunks, symbol vectors, file
summary vectors, and retrieval metadata. Payloads include repo id, repo name,
file path, language, commit SHA, chunk hash, chunk type, symbol name, line range,
indexed timestamp, text preview, and source kind. Qdrant must not store
approvals, audit logs, policy decisions, task state, or agent workflow state.
Ask and chat semantic retrieval read from this persistent Qdrant collection
filtered by repository id; production routes must not rebuild an in-memory index
or use deterministic test embeddings during a request.

Redis is motion. It is reserved for queues, indexing jobs, temporary locks,
short-lived cache entries, and rate or concurrency controls. Redis is never
required for permanent recovery.

The filesystem is evidence. It stores large local artifacts such as isolated
workspaces, patch files, validation logs, sandbox output, final reports, and
large model or tool output artifacts. PostgreSQL stores metadata and local paths
to these artifacts.

## Rebuild Boundaries

PostgreSQL backups are required for durable recovery. Qdrant collections can be
rebuilt from PostgreSQL repository records plus repository contents. Redis can be
discarded during recovery. Filesystem artifacts should be backed up when audit
or validation evidence must survive host replacement.

## Local-Only Assumptions

Default `LOCAL_ONLY` behavior is enabled through `SWITCH_LOCAL_ONLY=true`.
PostgreSQL, Qdrant, Redis, and vLLM endpoints must point to localhost, approved
Compose service names, or approved private/local network ranges. Source code,
prompts, embeddings, and secrets must not be sent to hosted LLM APIs or hosted
vector databases.

Secret-like files, key material, certificates, credentials, ignored files,
vendor folders, generated outputs, binaries, and oversized files are excluded
from indexing. Qdrant payloads store compact previews only and must not become a
secret store.

## Repo Q&A Flow

Repository Q&A is a read path over already-built indexes:

1. PostgreSQL verifies the repository exists and has a latest `ready` repo index.
2. The query is embedded through the local model gateway embedding role.
3. Qdrant searches `switch_code_chunks` with a `repo_id` payload filter.
4. Switch rehydrates bounded cited line ranges from the local filesystem.
5. Optional local model synthesis answers from retrieved context only.

If no ready index exists, `/ask` and repo-aware `/chat` return `409 Conflict`
with instructions to run `POST /repos/{repository_id}/index` or
`switch repo index <repo-id>`. If Qdrant or the embedding gateway is unavailable,
the request fails clearly instead of falling back to toy in-memory retrieval.

## Backup And Restore

Back up PostgreSQL first. It is the canonical state for approvals, policy,
audits, tasks, runs, and index status. Back up the artifact and workspace roots
when validation evidence or generated patches must be retained. Qdrant can be
snapshotted for faster restore, but it remains rebuildable. Redis persistence is
useful for operational continuity, not compliance recovery.
