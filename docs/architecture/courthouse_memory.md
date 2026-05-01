# Courthouse Memory

SWITCH memory is governed before it becomes context.

The courthouse layer separates raw evidence, extracted claims, verdicts, canonical state, open loops, context packets, and restore snapshots. Retrieval can suggest evidence, but retrieved memory is not automatically admissible, authoritative, or safe to export.

## Data Model

- `evidence_items` stores provenance for raw observations, including source, content hash, privacy class, exposure, workspace, adapter metadata, and optional raw text.
- `claims` stores extracted statements. Claims default to `candidate`.
- `verdicts` records deterministic decisions about claims, authority level, confidence, reason, supersession, contradiction, and appeal status.
- `canonical_state` stores current working truth. It can only be written from an accepted verdict with sufficient authority.
- `open_loops` stores unfinished work as first-class state.
- `context_snapshots` stores append-only restore traces of compiled context. A snapshot is not canonical truth.

## Gates

Privacy and exposure gates are enforced by `CourthouseService.compile_context`.

- `secrets_possible` is blocked from `tool_safe`, `repo_safe`, and `public_safe` packets.
- `private_fact` is blocked from `tool_safe` and `repo_safe` unless a later explicit policy override is added.
- `never_export` is never exported.
- Superseded claims are excluded from normal context.
- Contradicted claims appear as warnings, not facts.

## Context Compilation

The compiler returns structured packets with task interpretation, canonical state, active constraints, relevant decisions, facts, open loops, recent changes, selected raw evidence, contradiction warnings, exclusions, source references, and next actions.

Token budgeting uses a conservative local approximation until a platform token utility exists.

## Surfaces

The LAN web dashboard stays limited to chat and repo interface. Host dashboard remains the place for diagnostics, approvals, audit, metrics, and memory governance decisions.

The courthouse layer is exposed through API, CLI, and a local stdio MCP server entrypoint, `switch-mcp`. The MCP server is an adapter over the same `CourthouseService` APIs and does not open a network listener. It exposes context compilation, docket listing, verdict explanation, canonical state reads/writes, open loop updates, context diffs, memory health diagnostics, evidence submission, and candidate claim proposal.

## Future LLM Assistance

LLMs may later propose claim extraction or verdict recommendations, but correctness must not depend on them. LLM output must enter as candidate claims or review notes and still pass through deterministic courthouse adjudication. LLM-assisted extraction must never write verdicts, canonical state, or approval outcomes directly.

## Tests

Run:

`./.venv/bin/python -m pytest tests/test_courthouse.py tests/test_mcp_server.py`
