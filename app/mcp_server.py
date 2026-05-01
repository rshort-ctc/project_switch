from __future__ import annotations

import json
import sys
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.courthouse import CourthouseService, MemoryGovernanceError
from app.db.session import SessionLocal
from app.models.entities import CanonicalState, Claim, EvidenceItem, OpenLoop
from app.models.enums import ClaimStatus, ClaimType, Exposure, PrivacyClass

JsonDict = dict[str, Any]
ToolHandler = Callable[..., JsonDict]


def handle_request(request: JsonDict) -> JsonDict | None:
    request_id = request.get("id")
    method = request.get("method")
    result: JsonDict
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "switch", "version": __version__},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            tools_payload: list[JsonDict] = [tool for tool in TOOLS.values()]
            result = {"tools": tools_payload}
        elif method == "tools/call":
            params = _params(request)
            tool_name = str(params.get("name", ""))
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                raise ValueError(f"unknown tool: {tool_name}")
            result = _mcp_text(handler(**arguments))
        elif isinstance(method, str) and method.startswith("notifications/"):
            return None
        else:
            raise ValueError(f"unsupported method: {method}")
        return _success(request_id, result)
    except (MemoryGovernanceError, ValueError, TypeError) as exc:
        if request_id is None:
            return None
        return _error(request_id, code=-32000, message=str(exc))


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("JSON-RPC request must be an object")
            response = handle_request(request)
        except (json.JSONDecodeError, ValueError) as exc:
            response = _error(None, code=-32700, message=str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":"), default=str) + "\n")
            sys.stdout.flush()


def tool_submit_evidence(
    *,
    content: str,
    source_type: str,
    workspace: str | None = None,
    source_uri: str | None = None,
    privacy_class: str = PrivacyClass.INTERNAL,
    exposure: str = Exposure.PRIVATE_INTERNAL,
    metadata: dict[str, object] | None = None,
) -> JsonDict:
    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        evidence = service.submit_evidence(
            content=content,
            source_type=source_type,
            workspace=workspace,
            source_uri=source_uri,
            privacy_class=_enum(PrivacyClass, privacy_class),
            exposure=_enum(Exposure, exposure),
            metadata=metadata,
        )
        return {"evidence": _evidence_payload(evidence)}

    return _with_session(operation, commit=True)


def tool_propose_claims(
    *,
    evidence_id: str,
    default_claim_type: str = ClaimType.PROJECT_STATE,
    max_claims: int = 10,
) -> JsonDict:
    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        claims = service.propose_claims_from_evidence(
            evidence_id=evidence_id,
            default_claim_type=_enum(ClaimType, default_claim_type),
            max_claims=max_claims,
        )
        return {"claims": [_claim_payload(claim) for claim in claims]}

    return _with_session(operation, commit=True)


def tool_list_docket(
    *,
    workspace: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> JsonDict:
    def operation(session: Session, _service: CourthouseService) -> JsonDict:
        statement = select(Claim).order_by(Claim.created_at.desc(), Claim.id.desc()).limit(limit)
        if workspace is not None:
            statement = statement.where(Claim.workspace == workspace)
        if status is not None:
            statement = statement.where(Claim.status == _enum(ClaimStatus, status))
        claims = session.execute(statement).scalars()
        return {"claims": [_claim_payload(claim) for claim in claims]}

    return _with_session(operation)


def tool_explain_verdict(*, verdict_id: str) -> JsonDict:
    return _with_session(lambda _session, service: service.explain_verdict(verdict_id))


def tool_get_canonical_state(
    *, workspace: str | None = None, key: str | None = None
) -> JsonDict:
    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        rows = service.get_canonical_state(workspace=workspace, key=key)
        return {"canonical_state": [_canonical_payload(row) for row in rows]}

    return _with_session(operation)


def tool_set_canonical_state(
    *,
    key: str,
    value: dict[str, object],
    source_verdict_id: str,
    workspace: str | None = None,
    status: str = "active",
) -> JsonDict:
    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        row = service.set_canonical_state(
            key=key,
            value=value,
            source_verdict_id=source_verdict_id,
            workspace=workspace,
            status=status,
        )
        return {"canonical_state": _canonical_payload(row)}

    return _with_session(operation, commit=True)


def tool_open_loop_add(
    *,
    title: str,
    workspace: str | None = None,
    priority: int = 0,
    blocking_question: str | None = None,
    next_action: str | None = None,
    source_evidence_id: str | None = None,
    source_verdict_id: str | None = None,
) -> JsonDict:
    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        loop = service.open_loop(
            title=title,
            workspace=workspace,
            priority=priority,
            blocking_question=blocking_question,
            next_action=next_action,
            source_evidence_id=source_evidence_id,
            source_verdict_id=source_verdict_id,
        )
        return {"open_loop": _loop_payload(loop)}

    return _with_session(operation, commit=True)


def tool_open_loop_update(
    *,
    loop_id: str,
    title: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    blocking_question: str | None = None,
    next_action: str | None = None,
) -> JsonDict:
    updates = _drop_none(
        {
            "title": title,
            "status": status,
            "priority": priority,
            "blocking_question": blocking_question,
            "next_action": next_action,
        }
    )

    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        loop = service.update_loop(loop_id, **updates)
        return {"open_loop": _loop_payload(loop)}

    return _with_session(operation, commit=True)


def tool_open_loop_resolve(*, loop_id: str) -> JsonDict:
    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        loop = service.resolve_loop(loop_id)
        return {"open_loop": _loop_payload(loop)}

    return _with_session(operation, commit=True)


def tool_compile_context(
    *,
    task: str,
    workspace: str | None = None,
    mode: str | None = "normal",
    token_budget: int | None = 4000,
    exposure_ceiling: str = Exposure.TOOL_SAFE,
    include_raw_evidence: bool = True,
) -> JsonDict:
    def operation(_session: Session, service: CourthouseService) -> JsonDict:
        return service.compile_context(
            task=task,
            workspace=workspace,
            mode=mode,
            token_budget=token_budget,
            exposure_ceiling=_enum(Exposure, exposure_ceiling),
            include_raw_evidence=include_raw_evidence,
        )

    return _with_session(operation, commit=True)


def tool_context_diff(*, left_snapshot_id: str, right_snapshot_id: str) -> JsonDict:
    return _with_session(
        lambda _session, service: service.context_diff(left_snapshot_id, right_snapshot_id)
    )


def tool_memory_health(*, workspace: str | None = None) -> JsonDict:
    return _with_session(lambda _session, service: service.memory_health(workspace=workspace))


def _with_session(
    operation: Callable[[Session, CourthouseService], JsonDict], *, commit: bool = False
) -> JsonDict:
    with SessionLocal() as session:
        service = CourthouseService(session)
        result = operation(session, service)
        if commit:
            session.commit()
        return result


def _params(request: JsonDict) -> JsonDict:
    params = request.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("JSON-RPC params must be an object")
    return params


def _success(request_id: object, result: JsonDict) -> JsonDict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, *, code: int, message: str) -> JsonDict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _mcp_text(payload: JsonDict) -> JsonDict:
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, sort_keys=True, default=str)}
        ]
    }


def _enum[EnumT: StrEnum](enum_type: type[EnumT], value: str | EnumT) -> EnumT:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        message = f"invalid {enum_type.__name__}: {value}; expected one of {allowed}"
        raise ValueError(message) from exc


def _drop_none(values: dict[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def _evidence_payload(evidence: EvidenceItem) -> JsonDict:
    return {
        "id": evidence.id,
        "source_type": evidence.source_type,
        "source_uri": evidence.source_uri,
        "content_hash": evidence.content_hash,
        "workspace": evidence.workspace,
        "privacy_class": evidence.privacy_class,
        "exposure": evidence.exposure,
    }


def _claim_payload(claim: Claim) -> JsonDict:
    return {
        "id": claim.id,
        "normalized_text": claim.normalized_text,
        "claim_type": claim.claim_type,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": claim.object,
        "scope": claim.scope,
        "workspace": claim.workspace,
        "extracted_from_evidence_id": claim.extracted_from_evidence_id,
        "extractor": claim.extractor,
        "extractor_version": claim.extractor_version,
        "confidence": claim.confidence,
        "status": claim.status,
    }


def _canonical_payload(row: CanonicalState) -> JsonDict:
    return {
        "id": row.id,
        "key": row.key,
        "value": row.value_json,
        "workspace": row.workspace,
        "authority_level": row.authority_level,
        "source_verdict_id": row.source_verdict_id,
        "status": row.status,
    }


def _loop_payload(loop: OpenLoop) -> JsonDict:
    return {
        "id": loop.id,
        "title": loop.title,
        "workspace": loop.workspace,
        "status": loop.status,
        "priority": loop.priority,
        "blocking_question": loop.blocking_question,
        "next_action": loop.next_action,
        "source_evidence_id": loop.source_evidence_id,
        "source_verdict_id": loop.source_verdict_id,
    }


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "switch_memory_submit_evidence": tool_submit_evidence,
    "switch_memory_propose_claims": tool_propose_claims,
    "switch_memory_list_docket": tool_list_docket,
    "switch_memory_explain_verdict": tool_explain_verdict,
    "switch_memory_get_canonical_state": tool_get_canonical_state,
    "switch_memory_set_canonical_state": tool_set_canonical_state,
    "switch_memory_open_loop_add": tool_open_loop_add,
    "switch_memory_open_loop_update": tool_open_loop_update,
    "switch_memory_open_loop_resolve": tool_open_loop_resolve,
    "switch_memory_compile_context": tool_compile_context,
    "switch_memory_context_diff": tool_context_diff,
    "switch_memory_health": tool_memory_health,
}


def _tool(name: str, description: str, properties: JsonDict) -> JsonDict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        },
    }


TOOLS: dict[str, JsonDict] = {
    "switch_memory_submit_evidence": _tool(
        "switch_memory_submit_evidence",
        "Submit raw evidence to the governed memory archive.",
        {
            "content": {"type": "string"},
            "source_type": {"type": "string"},
            "workspace": {"type": ["string", "null"]},
            "source_uri": {"type": ["string", "null"]},
            "privacy_class": {"type": "string"},
            "exposure": {"type": "string"},
            "metadata": {"type": ["object", "null"]},
        },
    ),
    "switch_memory_propose_claims": _tool(
        "switch_memory_propose_claims",
        "Propose candidate claims from evidence without adjudicating or accepting them.",
        {
            "evidence_id": {"type": "string"},
            "default_claim_type": {"type": "string"},
            "max_claims": {"type": "integer", "minimum": 1},
        },
    ),
    "switch_memory_list_docket": _tool(
        "switch_memory_list_docket",
        "List filed claims on the courthouse docket.",
        {
            "workspace": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
            "limit": {"type": "integer", "minimum": 1},
        },
    ),
    "switch_memory_explain_verdict": _tool(
        "switch_memory_explain_verdict",
        "Explain a courthouse verdict.",
        {"verdict_id": {"type": "string"}},
    ),
    "switch_memory_get_canonical_state": _tool(
        "switch_memory_get_canonical_state",
        "Read accepted canonical state.",
        {"workspace": {"type": ["string", "null"]}, "key": {"type": ["string", "null"]}},
    ),
    "switch_memory_set_canonical_state": _tool(
        "switch_memory_set_canonical_state",
        "Set canonical state from an accepted valid verdict.",
        {
            "key": {"type": "string"},
            "value": {"type": "object"},
            "source_verdict_id": {"type": "string"},
            "workspace": {"type": ["string", "null"]},
            "status": {"type": "string"},
        },
    ),
    "switch_memory_open_loop_add": _tool(
        "switch_memory_open_loop_add",
        "Add an open loop to governed memory.",
        {
            "title": {"type": "string"},
            "workspace": {"type": ["string", "null"]},
            "priority": {"type": "integer"},
            "blocking_question": {"type": ["string", "null"]},
            "next_action": {"type": ["string", "null"]},
            "source_evidence_id": {"type": ["string", "null"]},
            "source_verdict_id": {"type": ["string", "null"]},
        },
    ),
    "switch_memory_open_loop_update": _tool(
        "switch_memory_open_loop_update",
        "Update an open loop.",
        {
            "loop_id": {"type": "string"},
            "title": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
            "priority": {"type": ["integer", "null"]},
            "blocking_question": {"type": ["string", "null"]},
            "next_action": {"type": ["string", "null"]},
        },
    ),
    "switch_memory_open_loop_resolve": _tool(
        "switch_memory_open_loop_resolve",
        "Resolve an open loop.",
        {"loop_id": {"type": "string"}},
    ),
    "switch_memory_compile_context": _tool(
        "switch_memory_compile_context",
        "Compile governed memory context with workspace, privacy, and exposure gates.",
        {
            "task": {"type": "string"},
            "workspace": {"type": ["string", "null"]},
            "mode": {"type": ["string", "null"]},
            "token_budget": {"type": ["integer", "null"]},
            "exposure_ceiling": {"type": "string"},
            "include_raw_evidence": {"type": "boolean"},
        },
    ),
    "switch_memory_context_diff": _tool(
        "switch_memory_context_diff",
        "Diff two context restore snapshots.",
        {"left_snapshot_id": {"type": "string"}, "right_snapshot_id": {"type": "string"}},
    ),
    "switch_memory_health": _tool(
        "switch_memory_health",
        "Report courthouse memory health diagnostics.",
        {"workspace": {"type": ["string", "null"]}},
    ),
}


if __name__ == "__main__":
    main()
