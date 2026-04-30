from sqlalchemy.orm import Session

from app.api.routes.approvals import approve, deny, list_pending_approvals
from app.models.enums import AgentRunStatus, ApprovalStatus
from app.schemas.durable import ApprovalDecisionRequest
from app.services.runs import RunService


def create_pending_approval(session: Session) -> tuple[str, str]:
    service = RunService(session)
    user = service.create_user(email="approver@example.test", display_name="Approver")
    repository = service.register_repository(
        name="approval-repo",
        local_path="/tmp/approval-repo",
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Approval task",
        description="Exercise approval API",
    )
    run = service.create_agent_run(task_id=task.id, base_branch="feature/approval")
    approval = service.request_approval(
        agent_run_id=run.id,
        requested_by_user_id=user.id,
        requested_action="apply_patch",
        risk_level="high",
        reason="Patch mutates workspace",
        diff_summary="1 file(s), +1/-1",
    )
    return user.id, approval.id


def test_approval_api_approve_and_list_pending(session: Session) -> None:
    user_id, approval_id = create_pending_approval(session)

    pending = list_pending_approvals(session)
    approved = approve(
        approval_id,
        ApprovalDecisionRequest(decided_by_user_id=user_id, decision_note="looks safe"),
        session,
    )

    assert pending[0].requested_action == "apply_patch"
    assert pending[0].risk_level == "high"
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.decided_by_user_id == user_id


def test_approval_api_deny_stops_run(session: Session) -> None:
    user_id, approval_id = create_pending_approval(session)

    denied = deny(
        approval_id,
        ApprovalDecisionRequest(decided_by_user_id=user_id, decision_note="too broad"),
        session,
    )

    assert denied.status == ApprovalStatus.REJECTED
    assert denied.denial_reason == "too broad"
    approval = RunService(session).approvals.get(approval_id)
    assert approval is not None
    run = RunService(session).runs.get(approval.agent_run_id)
    assert run is not None
    assert AgentRunStatus(run.status) is AgentRunStatus.FAILED
