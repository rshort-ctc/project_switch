from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.cli_api import AuditLogResponse
from app.schemas.durable import AuditEventRead
from app.services.audit import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])

SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=AuditLogResponse)
def audit_log(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AuditLogResponse:
    events = [
        AuditEventRead.model_validate(event)
        for event in AuditService(session).list_recent(limit=limit)
    ]
    return AuditLogResponse(events=events)
