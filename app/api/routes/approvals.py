from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.entities import ApprovalRequest
from app.models.enums import ApprovalStatus
from app.schemas.durable import ApprovalDecisionRequest, ApprovalRequestRead
from app.services.exceptions import EntityNotFoundError, InvalidStatusTransitionError
from app.services.runs import RunService

router = APIRouter(prefix="/approvals", tags=["approvals"])

SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("/pending", response_model=list[ApprovalRequestRead])
def list_pending_approvals(session: SessionDependency) -> list[ApprovalRequest]:
    return list(RunService(session).approvals.list_pending())


@router.get("/{approval_request_id}", response_model=ApprovalRequestRead)
def get_approval(
    approval_request_id: str,
    session: SessionDependency,
) -> ApprovalRequest:
    approval = RunService(session).approvals.get(approval_request_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found")
    return approval


@router.post("/{approval_request_id}/approve", response_model=ApprovalRequestRead)
def approve(
    approval_request_id: str,
    request: ApprovalDecisionRequest,
    session: SessionDependency,
) -> ApprovalRequest:
    return _decide(
        approval_request_id=approval_request_id,
        request=request,
        decision=ApprovalStatus.APPROVED,
        session=session,
    )


@router.post("/{approval_request_id}/deny", response_model=ApprovalRequestRead)
def deny(
    approval_request_id: str,
    request: ApprovalDecisionRequest,
    session: SessionDependency,
) -> ApprovalRequest:
    return _decide(
        approval_request_id=approval_request_id,
        request=request,
        decision=ApprovalStatus.REJECTED,
        session=session,
    )


def _decide(
    *,
    approval_request_id: str,
    request: ApprovalDecisionRequest,
    decision: ApprovalStatus,
    session: Session,
) -> ApprovalRequest:
    service = RunService(session)
    try:
        approval = service.decide_approval(
            approval_request_id=approval_request_id,
            decided_by_user_id=request.decided_by_user_id,
            status=decision,
            decision_note=request.decision_note,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    return approval
