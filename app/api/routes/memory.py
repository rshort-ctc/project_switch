from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.courthouse import CourthouseService, MemoryGovernanceError
from app.db.session import get_db_session
from app.models.enums import AuthorityLevel, ClaimType, Exposure, PrivacyClass, Verdict

router = APIRouter(prefix="/memory", tags=["memory"])

SessionDependency = Annotated[Session, Depends(get_db_session)]


class EvidenceSubmitRequest(BaseModel):
    content: str = Field(min_length=1)
    source_type: str = Field(min_length=1, max_length=80)
    workspace: str | None = Field(default=None, max_length=200)
    source_uri: str | None = Field(default=None, max_length=1024)
    privacy_class: PrivacyClass = PrivacyClass.INTERNAL
    exposure: Exposure = Exposure.PRIVATE_INTERNAL
    metadata: dict[str, object] = Field(default_factory=dict)


class ClaimSubmitRequest(BaseModel):
    evidence_id: str
    normalized_text: str | None = None
    claim_type: ClaimType = ClaimType.PROJECT_STATE
    subject: str | None = None
    predicate: str | None = None
    object_value: str | None = None
    scope: str | None = None
    workspace: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)


class VerdictRequest(BaseModel):
    claim_id: str
    verdict: Verdict = Verdict.ACCEPTED
    authority_level: AuthorityLevel = AuthorityLevel.USER_STATEMENT
    confidence: float = Field(default=1.0, ge=0, le=1)
    decided_by: str = Field(default="host-dashboard", max_length=160)
    reason: str | None = None
    supersedes_claim_id: str | None = None
    contradicts_claim_id: str | None = None


class CanonicalStateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=300)
    value: dict[str, object]
    source_verdict_id: str
    workspace: str | None = Field(default=None, max_length=200)


class OpenLoopRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    workspace: str | None = Field(default=None, max_length=200)
    priority: int = 0
    blocking_question: str | None = None
    next_action: str | None = None


class OpenLoopUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    status: str | None = Field(default=None, max_length=40)
    priority: int | None = None
    blocking_question: str | None = None
    next_action: str | None = None


class ContextCompileRequest(BaseModel):
    task: str = Field(min_length=1)
    workspace: str | None = Field(default=None, max_length=200)
    mode: str | None = "normal"
    token_budget: int | None = Field(default=4000, ge=1)
    exposure_ceiling: Exposure = Exposure.TOOL_SAFE
    include_raw_evidence: bool = True


@router.post("/evidence")
def submit_evidence(
    request: EvidenceSubmitRequest, session: SessionDependency
) -> dict[str, object]:
    service = CourthouseService(session)
    evidence = service.submit_evidence(
        content=request.content,
        source_type=request.source_type,
        source_uri=request.source_uri,
        privacy_class=request.privacy_class,
        exposure=request.exposure,
        workspace=request.workspace,
        metadata=request.metadata,
    )
    session.commit()
    return {"id": evidence.id, "content_hash": evidence.content_hash}


@router.post("/claims")
def submit_claim(request: ClaimSubmitRequest, session: SessionDependency) -> dict[str, object]:
    try:
        claim = CourthouseService(session).extract_or_submit_claim(
            evidence_id=request.evidence_id,
            normalized_text=request.normalized_text,
            claim_type=request.claim_type,
            subject=request.subject,
            predicate=request.predicate,
            object_value=request.object_value,
            scope=request.scope,
            workspace=request.workspace,
            confidence=request.confidence,
        )
    except MemoryGovernanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    session.commit()
    return {"id": claim.id, "status": claim.status}


@router.post("/verdicts")
def adjudicate_claim(request: VerdictRequest, session: SessionDependency) -> dict[str, object]:
    try:
        verdict = CourthouseService(session).adjudicate_claim(**request.model_dump())
    except MemoryGovernanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    session.commit()
    return {
        "id": verdict.id,
        "verdict": verdict.verdict,
        "authority_level": verdict.authority_level,
    }


@router.get("/verdicts/{verdict_id}/explain")
def explain_verdict(verdict_id: str, session: SessionDependency) -> dict[str, object]:
    try:
        return CourthouseService(session).explain_verdict(verdict_id)
    except MemoryGovernanceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/canonical-state")
def set_canonical_state(
    request: CanonicalStateRequest, session: SessionDependency
) -> dict[str, object]:
    try:
        state = CourthouseService(session).set_canonical_state(
            key=request.key,
            value=request.value,
            source_verdict_id=request.source_verdict_id,
            workspace=request.workspace,
        )
    except MemoryGovernanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    session.commit()
    return {"id": state.id, "key": state.key, "workspace": state.workspace}


@router.get("/canonical-state")
def get_canonical_state(
    session: SessionDependency,
    workspace: str | None = None,
    key: str | None = None,
) -> dict[str, object]:
    rows = CourthouseService(session).get_canonical_state(workspace=workspace, key=key)
    return {
        "state": [
            {
                "id": row.id,
                "key": row.key,
                "value": row.value_json,
                "workspace": row.workspace,
                "authority_level": row.authority_level,
                "source_verdict_id": row.source_verdict_id,
            }
            for row in rows
        ]
    }


@router.post("/open-loops")
def add_open_loop(request: OpenLoopRequest, session: SessionDependency) -> dict[str, object]:
    loop = CourthouseService(session).open_loop(**request.model_dump())
    session.commit()
    return {"id": loop.id, "status": loop.status}


@router.post("/open-loops/{loop_id}")
def update_open_loop(
    loop_id: str, request: OpenLoopUpdateRequest, session: SessionDependency
) -> dict[str, object]:
    try:
        loop = CourthouseService(session).update_loop(
            loop_id, **{k: v for k, v in request.model_dump().items() if v is not None}
        )
    except MemoryGovernanceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    return {"id": loop.id, "status": loop.status}


@router.post("/open-loops/{loop_id}/resolve")
def resolve_open_loop(loop_id: str, session: SessionDependency) -> dict[str, object]:
    try:
        loop = CourthouseService(session).resolve_loop(loop_id)
    except MemoryGovernanceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    return {"id": loop.id, "status": loop.status}


@router.post("/context/compile")
def compile_context(
    request: ContextCompileRequest, session: SessionDependency
) -> dict[str, object]:
    packet = CourthouseService(session).compile_context(**request.model_dump())
    session.commit()
    return packet


@router.get("/health")
def memory_health(session: SessionDependency, workspace: str | None = None) -> dict[str, object]:
    return CourthouseService(session).memory_health(workspace=workspace)
