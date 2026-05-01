from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories import AuditEventRepository
from app.models.entities import AuditEvent
from app.models.enums import AuditStatus
from app.security.action_policy import ActionClass
from app.security.redaction import redact_secrets

SECRET_METADATA_KEYS = ("api_key", "apikey", "token", "secret", "password", "credential")


@dataclass(frozen=True)
class AuditLogRecord:
    id: str
    timestamp: datetime
    actor: str | None
    action: str
    action_class: ActionClass
    target_type: str
    target_id: str | None
    summary: str
    metadata: dict[str, object]
    status: AuditStatus
    correlation_id: str | None


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
            actor=actor_user_id,
            action_class=ActionClass.READ_ONLY.value,
            metadata_json={},
            status=AuditStatus.EXECUTED.value,
            correlation_id=trace_id,
            actor_user_id=actor_user_id,
            agent_run_id=agent_run_id,
            trace_id=trace_id,
        )

    def record_action(
        self,
        *,
        actor: str,
        action: str,
        action_class: ActionClass,
        target_type: str,
        target_id: str | None,
        summary: str,
        status: AuditStatus,
        metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
        actor_user_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> AuditEvent:
        return self.repository.create(
            actor=actor,
            actor_user_id=actor_user_id,
            agent_run_id=agent_run_id,
            event_type=action,
            action_class=action_class.value,
            subject_type=target_type,
            subject_id=target_id,
            summary=redact_secrets(summary) or "",
            metadata_json=_redact_metadata(metadata or {}),
            status=status.value,
            trace_id=correlation_id,
            correlation_id=correlation_id,
        )

    def list_for_run(self, agent_run_id: str) -> Sequence[AuditEvent]:
        return self.repository.list_for_run(agent_run_id)

    def list_recent(self, *, limit: int = 100) -> Sequence[AuditEvent]:
        return self.repository.list_recent(limit=limit)

    def list_by_correlation_id(self, correlation_id: str) -> Sequence[AuditEvent]:
        return self.repository.list_by_correlation_id(correlation_id)

    def list_for_target(self, target_type: str, target_id: str | None) -> Sequence[AuditEvent]:
        return self.repository.list_for_target(target_type, target_id)

    @staticmethod
    def to_log_record(event: AuditEvent) -> AuditLogRecord:
        return AuditLogRecord(
            id=event.id,
            timestamp=event.created_at,
            actor=event.actor or event.actor_user_id,
            action=event.event_type,
            action_class=ActionClass(event.action_class or ActionClass.READ_ONLY.value),
            target_type=event.subject_type,
            target_id=event.subject_id,
            summary=event.summary,
            metadata=event.metadata_json or {},
            status=AuditStatus(event.status or AuditStatus.EXECUTED.value),
            correlation_id=event.correlation_id or event.trace_id,
        )


def _redact_metadata(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_secret_key(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_secrets(value) or ""
    if isinstance(value, dict):
        return {
            str(item_key): _redact_metadata(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_metadata(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(secret_key in lowered for secret_key in SECRET_METADATA_KEYS)
