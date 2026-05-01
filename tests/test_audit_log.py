from sqlalchemy.orm import Session

from app.models.enums import AuditStatus
from app.security.action_policy import ActionClass
from app.services.audit import AuditService


def test_audit_log_events_can_be_created_and_projected(session: Session) -> None:
    audit = AuditService(session)

    event = audit.record_action(
        actor="operator@example.test",
        action="draft_vendor_email",
        action_class=ActionClass.DRAFT_ONLY,
        target_type="ticket",
        target_id="TICKET-100",
        summary="Drafted vendor email with token=secret-value",
        metadata={
            "ticket": "TICKET-100",
            "api_key": "local-secret-value",
            "details": {"password": "hunter2", "note": "safe operational note"},
        },
        status=AuditStatus.DRAFTED,
        correlation_id="corr-100",
    )
    record = audit.to_log_record(event)

    assert record.id == event.id
    assert record.timestamp == event.created_at
    assert record.actor == "operator@example.test"
    assert record.action == "draft_vendor_email"
    assert record.action_class is ActionClass.DRAFT_ONLY
    assert record.target_type == "ticket"
    assert record.target_id == "TICKET-100"
    assert record.status is AuditStatus.DRAFTED
    assert record.correlation_id == "corr-100"
    assert "secret-value" not in record.summary
    assert record.metadata["api_key"] == "[REDACTED]"
    assert record.metadata["details"]["password"] == "[REDACTED]"


def test_audit_log_events_can_be_queried(session: Session) -> None:
    audit = AuditService(session)
    audit.record_action(
        actor="operator@example.test",
        action="summarize_ticket",
        action_class=ActionClass.READ_ONLY,
        target_type="ticket",
        target_id="TICKET-101",
        summary="Summarized ticket",
        status=AuditStatus.EXECUTED,
        correlation_id="corr-101",
    )
    audit.record_action(
        actor="operator@example.test",
        action="export_sensitive_data",
        action_class=ActionClass.BLOCKED,
        target_type="export",
        target_id="EXPORT-1",
        summary="Blocked export request",
        status=AuditStatus.BLOCKED,
        correlation_id="corr-101",
    )

    correlated = audit.list_by_correlation_id("corr-101")
    target_events = audit.list_for_target("ticket", "TICKET-101")
    recent = audit.list_recent(limit=10)

    assert [event.event_type for event in correlated] == [
        "summarize_ticket",
        "export_sensitive_data",
    ]
    assert [event.event_type for event in target_events] == ["summarize_ticket"]
    assert {event.event_type for event in recent} >= {"summarize_ticket", "export_sensitive_data"}


def test_audit_status_values_match_phase_1c_contract() -> None:
    assert {status.value for status in AuditStatus} == {
        "proposed",
        "drafted",
        "approved",
        "rejected",
        "executed",
        "failed",
        "blocked",
    }
