from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.db.repositories import AuditEventRepository
from app.models.entities import AuditEvent
from app.security.redaction import redact_secrets


class AuditService:
    def __init__(self, session: Session) -> None:
        self.repository = AuditEventRepository(session)

    def record(
        self,
        *,
        event_type: str,
        summary: str,
        subject_type: str,
        subject_id: str | None,
        actor_user_id: str | None = None,
        agent_run_id: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEvent:
        return self.repository.create(
            event_type=event_type,
            summary=redact_secrets(summary) or "",
            subject_type=subject_type,
            subject_id=subject_id,
            actor_user_id=actor_user_id,
            agent_run_id=agent_run_id,
            trace_id=trace_id,
        )

    def list_for_run(self, agent_run_id: str) -> Sequence[AuditEvent]:
        return self.repository.list_for_run(agent_run_id)

    def list_recent(self, *, limit: int = 100) -> Sequence[AuditEvent]:
        return self.repository.list_recent(limit=limit)
