import pytest
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent
from app.models.enums import ApprovalStatus, AuditStatus
from app.security.action_policy import ActionClass
from app.services.approval_queue import ApprovalQueueService
from app.services.exceptions import InvalidStatusTransitionError


def test_approval_queue_creates_pending_request_and_audit_event(session: Session) -> None:
    service = ApprovalQueueService(session)

    approval = service.create_request(
        requested_by="operator@example.test",
        action="send_vendor_email",
        target_type="ticket",
        target_id="TCK-100",
        proposed_payload={"subject": "Provider escalation draft"},
        risk_summary="External vendor communication requires review.",
        correlation_id="corr-approval-1",
    )

    assert approval.status == ApprovalStatus.PENDING
    assert approval.requested_by == "operator@example.test"
    assert approval.action == "send_vendor_email"
    assert approval.action_class == ActionClass.REQUIRES_APPROVAL.value
    assert approval.target_type == "ticket"
    assert approval.target_id == "TCK-100"
    assert approval.proposed_payload == {"subject": "Provider escalation draft"}
    assert approval.risk_summary == "External vendor communication requires review."
    assert approval.audit_event_id is not None

    audit_event = session.get(AuditEvent, approval.audit_event_id)
    assert audit_event is not None
    assert audit_event.event_type == "approval.requested"
    assert audit_event.status == AuditStatus.PROPOSED.value
    assert audit_event.subject_type == "approval_request"
    assert audit_event.subject_id == approval.id
    assert audit_event.correlation_id == "corr-approval-1"


def test_approval_queue_lists_and_reviews_without_executing_actions(
    session: Session,
) -> None:
    service = ApprovalQueueService(session)
    first = service.create_request(
        requested_by="operator@example.test",
        action="send_vendor_email",
        target_type="ticket",
        target_id="TCK-101",
        proposed_payload={"body": "draft only"},
        risk_summary="External message must be reviewed.",
    )
    second = service.create_request(
        requested_by="operator@example.test",
        action="modify_ticket_record",
        target_type="ticket",
        target_id="TCK-102",
        proposed_payload={"status": "pending_vendor"},
        risk_summary="Record mutation requires approval.",
    )
    third = service.create_request(
        requested_by="operator@example.test",
        action="change_network_config",
        target_type="site",
        target_id="SITE-1",
        proposed_payload={"change": "blocked skeleton only"},
        risk_summary="Network changes require admin review.",
    )

    assert [request.id for request in service.list_pending()] == [
        first.id,
        second.id,
        third.id,
    ]

    approved = service.approve(first.id, reviewed_by="supervisor@example.test")
    rejected = service.reject(
        second.id,
        reviewed_by="supervisor@example.test",
        review_note="Missing ticket owner approval.",
    )
    cancelled = service.cancel(
        third.id,
        reviewed_by="operator@example.test",
        review_note="Request replaced by a safer draft.",
    )

    assert approved.status == ApprovalStatus.APPROVED
    assert approved.reviewed_by == "supervisor@example.test"
    assert approved.reviewed_at is not None
    assert approved.decided_by_user_id is None
    assert rejected.status == ApprovalStatus.REJECTED
    assert rejected.denial_reason == "Missing ticket owner approval."
    assert cancelled.status == ApprovalStatus.CANCELLED
    assert cancelled.review_note == "Request replaced by a safer draft."
    assert service.list_pending() == []
    assert {request.id for request in service.list_requests()} == {
        first.id,
        second.id,
        third.id,
    }


def test_approval_status_values_include_phase_1d_contract() -> None:
    assert {status.value for status in ApprovalStatus} >= {
        "pending",
        "approved",
        "rejected",
        "cancelled",
        "expired",
    }


def test_non_pending_approval_cannot_be_reviewed_twice(session: Session) -> None:
    service = ApprovalQueueService(session)
    approval = service.create_request(
        requested_by="operator@example.test",
        action="send_vendor_email",
        target_type="ticket",
        target_id="TCK-103",
        proposed_payload={},
        risk_summary="External message must be reviewed.",
    )

    service.approve(approval.id, reviewed_by="supervisor@example.test")

    with pytest.raises(InvalidStatusTransitionError):
        service.reject(
            approval.id,
            reviewed_by="supervisor@example.test",
            review_note="Cannot reject after approval.",
        )
