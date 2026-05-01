from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.repositories import ApprovalRequestRepository
from app.models.entities import ApprovalRequest
from app.models.enums import ApprovalStatus, AuditStatus
from app.security.action_policy import ActionClass, classify_action
from app.services.audit import AuditService
from app.services.exceptions import EntityNotFoundError, InvalidStatusTransitionError

APPROVAL_AUDIT_STATUSES: dict[ApprovalStatus, AuditStatus] = {
    ApprovalStatus.APPROVED: AuditStatus.APPROVED,
    ApprovalStatus.REJECTED: AuditStatus.REJECTED,
    ApprovalStatus.CANCELLED: AuditStatus.BLOCKED,
}


class ApprovalQueueService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.approvals = ApprovalRequestRepository(session)
        self.audit = AuditService(session)

    def create_request(
        self,
        *,
        requested_by: str,
        action: str,
        target_type: str,
        target_id: str,
        risk_summary: str,
        proposed_payload: dict[str, object] | None = None,
        action_class: ActionClass | str | None = None,
        correlation_id: str | None = None,
        requested_by_user_id: str | None = None,
        task_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> ApprovalRequest:
        resolved_action_class = _resolve_action_class(action, action_class)
        approval = self.approvals.create(
            task_id=task_id,
            agent_run_id=agent_run_id,
            requested_by_user_id=requested_by_user_id,
            reason=risk_summary,
            requested_action=action,
            requested_by=requested_by,
            action=action,
            action_class=resolved_action_class.value,
            target_type=target_type,
            target_id=target_id,
            proposed_payload=proposed_payload or {},
            risk_summary=risk_summary,
        )
        audit_event = self.audit.record_action(
            actor=requested_by,
            action="approval.requested",
            action_class=resolved_action_class,
            target_type="approval_request",
            target_id=approval.id,
            summary=f"approval requested for {action}: {risk_summary}",
            status=AuditStatus.PROPOSED,
            metadata={
                "requested_action": action,
                "target_type": target_type,
                "target_id": target_id,
            },
            correlation_id=correlation_id,
            actor_user_id=requested_by_user_id,
            agent_run_id=agent_run_id,
        )
        approval.audit_event_id = audit_event.id
        self.session.flush()
        return approval

    def list_requests(self, status: ApprovalStatus | None = None) -> Sequence[ApprovalRequest]:
        if status is None:
            return self.approvals.list()
        return self.approvals.list_by_status(status)

    def list_pending(self) -> Sequence[ApprovalRequest]:
        return self.approvals.list_pending()

    def approve(
        self,
        approval_request_id: str,
        *,
        reviewed_by: str,
        review_note: str | None = None,
    ) -> ApprovalRequest:
        return self._review(
            approval_request_id,
            reviewed_by=reviewed_by,
            review_note=review_note,
            status=ApprovalStatus.APPROVED,
        )

    def reject(
        self,
        approval_request_id: str,
        *,
        reviewed_by: str,
        review_note: str | None = None,
    ) -> ApprovalRequest:
        return self._review(
            approval_request_id,
            reviewed_by=reviewed_by,
            review_note=review_note,
            status=ApprovalStatus.REJECTED,
        )

    def cancel(
        self,
        approval_request_id: str,
        *,
        reviewed_by: str,
        review_note: str | None = None,
    ) -> ApprovalRequest:
        return self._review(
            approval_request_id,
            reviewed_by=reviewed_by,
            review_note=review_note,
            status=ApprovalStatus.CANCELLED,
        )

    def _review(
        self,
        approval_request_id: str,
        *,
        reviewed_by: str,
        review_note: str | None,
        status: ApprovalStatus,
    ) -> ApprovalRequest:
        approval = self.approvals.get(approval_request_id)
        if approval is None:
            raise EntityNotFoundError(f"approval request not found: {approval_request_id}")
        if ApprovalStatus(approval.status) is not ApprovalStatus.PENDING:
            raise InvalidStatusTransitionError("approval request has already been reviewed")

        now = datetime.now(UTC)
        approval.status = status
        approval.reviewed_by = reviewed_by
        approval.reviewed_at = now
        approval.review_note = review_note
        approval.decided_at = now
        approval.decision_note = review_note
        if status in {ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED}:
            approval.denial_reason = review_note

        self.audit.record_action(
            actor=reviewed_by,
            action=f"approval.{status.value}",
            action_class=_resolve_action_class(
                approval.action or approval.requested_action,
                approval.action_class,
            ),
            target_type="approval_request",
            target_id=approval.id,
            summary=f"approval {status.value}: {approval.action or approval.requested_action}",
            status=APPROVAL_AUDIT_STATUSES[status],
            metadata={
                "requested_action": approval.action or approval.requested_action,
                "target_type": approval.target_type or "unknown",
                "target_id": approval.target_id or "",
            },
            agent_run_id=approval.agent_run_id,
        )
        self.session.flush()
        return approval


def _resolve_action_class(action: str, action_class: ActionClass | str | None) -> ActionClass:
    if isinstance(action_class, ActionClass):
        return action_class
    if action_class:
        return ActionClass(action_class)
    return classify_action(action)
