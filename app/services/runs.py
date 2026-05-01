from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.repositories import (
    AgentRunRepository,
    AgentStepRepository,
    ApprovalRequestRepository,
    RepositoryRepository,
    TaskRepository,
    UserRepository,
)
from app.models.entities import AgentRun, AgentStep, ApprovalRequest, Repository, Task, User
from app.models.enums import AgentRunStatus, AgentStepStatus, ApprovalStatus, TaskStatus
from app.security.action_policy import ActionClass
from app.services.audit import AuditService
from app.services.exceptions import EntityNotFoundError, InvalidStatusTransitionError

RUN_TRANSITIONS: dict[AgentRunStatus, set[AgentRunStatus]] = {
    AgentRunStatus.PENDING: {AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED},
    AgentRunStatus.RUNNING: {
        AgentRunStatus.WAITING_APPROVAL,
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    },
    AgentRunStatus.WAITING_APPROVAL: {
        AgentRunStatus.RUNNING,
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    },
    AgentRunStatus.COMPLETED: set(),
    AgentRunStatus.FAILED: set(),
    AgentRunStatus.CANCELLED: set(),
}


class RunService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.repositories = RepositoryRepository(session)
        self.tasks = TaskRepository(session)
        self.runs = AgentRunRepository(session)
        self.steps = AgentStepRepository(session)
        self.approvals = ApprovalRequestRepository(session)
        self.audit = AuditService(session)

    def create_user(self, *, email: str, display_name: str) -> User:
        user = self.users.create(email=email, display_name=display_name)
        self.audit.record(
            event_type="user.created",
            summary=f"user created: {email}",
            subject_type="user",
            subject_id=user.id,
            actor_user_id=user.id,
        )
        return user

    def register_repository(self, *, name: str, local_path: str, default_branch: str) -> Repository:
        repository = self.repositories.create(
            name=name,
            local_path=local_path,
            default_branch=default_branch,
        )
        self.audit.record(
            event_type="repository.created",
            summary=f"repository registered: {name}",
            subject_type="repository",
            subject_id=repository.id,
        )
        return repository

    def create_task(
        self,
        *,
        repository_id: str,
        created_by_user_id: str,
        title: str,
        description: str,
    ) -> Task:
        task = self.tasks.create(
            repository_id=repository_id,
            created_by_user_id=created_by_user_id,
            title=title,
            description=description,
        )
        self.audit.record(
            event_type="task.created",
            summary=f"task created: {title}",
            subject_type="task",
            subject_id=task.id,
            actor_user_id=created_by_user_id,
        )
        return task

    def create_agent_run(
        self,
        *,
        task_id: str,
        base_branch: str,
        target_branch: str | None = None,
        model_name: str | None = None,
    ) -> AgentRun:
        run = self.runs.create(
            task_id=task_id,
            base_branch=base_branch,
            target_branch=target_branch,
            model_name=model_name,
        )
        self.audit.record(
            event_type="agent_run.created",
            summary=f"agent run created from {base_branch}",
            subject_type="agent_run",
            subject_id=run.id,
            agent_run_id=run.id,
        )
        return run

    def transition_run(self, *, agent_run_id: str, status: AgentRunStatus) -> AgentRun:
        run = self.runs.get(agent_run_id)
        if run is None:
            raise EntityNotFoundError(f"agent run not found: {agent_run_id}")

        current = AgentRunStatus(run.status)
        if status not in RUN_TRANSITIONS[current]:
            raise InvalidStatusTransitionError(f"cannot transition run from {current} to {status}")

        now = datetime.now(UTC)
        run.status = status
        if status is AgentRunStatus.RUNNING and run.started_at is None:
            run.started_at = now
        if status in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}:
            run.completed_at = now

        self.audit.record(
            event_type="agent_run.status_changed",
            summary=f"agent run status changed: {current} -> {status}",
            subject_type="agent_run",
            subject_id=run.id,
            agent_run_id=run.id,
        )
        self.session.flush()
        return run

    def create_step(self, *, agent_run_id: str, sequence: int, name: str) -> AgentStep:
        step = self.steps.create(agent_run_id=agent_run_id, sequence=sequence, name=name)
        self.audit.record(
            event_type="agent_step.created",
            summary=f"agent step created: {name}",
            subject_type="agent_step",
            subject_id=step.id,
            agent_run_id=agent_run_id,
        )
        return step

    def request_approval(
        self,
        *,
        agent_run_id: str,
        requested_by_user_id: str,
        reason: str,
        requested_action: str = "unspecified",
        risk_level: str = "medium",
        diff_summary: str | None = None,
        command: str | None = None,
    ) -> ApprovalRequest:
        run = self.runs.get(agent_run_id)
        if run is None:
            raise EntityNotFoundError(f"agent run not found: {agent_run_id}")
        approval = self.approvals.create(
            task_id=run.task_id,
            agent_run_id=agent_run_id,
            requested_by_user_id=requested_by_user_id,
            reason=reason,
            requested_action=requested_action,
            risk_level=risk_level,
            diff_summary=diff_summary,
            command=command,
            requested_by=requested_by_user_id,
            action=requested_action,
            action_class=ActionClass.REQUIRES_APPROVAL.value,
            target_type="agent_run",
            target_id=agent_run_id,
            proposed_payload={
                "risk_level": risk_level,
                "diff_summary": diff_summary,
                "command": command,
            },
            risk_summary=reason,
        )
        current = AgentRunStatus(run.status)
        if current is AgentRunStatus.PENDING:
            self.transition_run(agent_run_id=agent_run_id, status=AgentRunStatus.RUNNING)
            current = AgentRunStatus.RUNNING
        if current is AgentRunStatus.RUNNING:
            self.transition_run(agent_run_id=agent_run_id, status=AgentRunStatus.WAITING_APPROVAL)
        audit_event = self.audit.record(
            event_type="approval.requested",
            summary=f"approval requested: {requested_action} risk={risk_level}: {reason}",
            subject_type="approval_request",
            subject_id=approval.id,
            actor_user_id=requested_by_user_id,
            agent_run_id=agent_run_id,
        )
        approval.audit_event_id = audit_event.id
        self.session.flush()
        return approval

    def decide_approval(
        self,
        *,
        approval_request_id: str,
        decided_by_user_id: str,
        status: ApprovalStatus,
        decision_note: str | None = None,
    ) -> ApprovalRequest:
        if status not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise InvalidStatusTransitionError("approval decisions must be approved or rejected")
        approval = self.approvals.get(approval_request_id)
        if approval is None:
            raise EntityNotFoundError(f"approval request not found: {approval_request_id}")
        if ApprovalStatus(approval.status) is not ApprovalStatus.PENDING:
            raise InvalidStatusTransitionError("approval request has already been decided")

        approval.status = status
        approval.decided_by_user_id = decided_by_user_id
        approval.decision_note = decision_note
        approval.reviewed_by = decided_by_user_id
        approval.review_note = decision_note
        if status is ApprovalStatus.REJECTED:
            approval.denial_reason = decision_note
        approval.decided_at = datetime.now(UTC)
        approval.reviewed_at = approval.decided_at
        run = self.runs.get(approval.agent_run_id) if approval.agent_run_id else None
        if run is not None and AgentRunStatus(run.status) is AgentRunStatus.WAITING_APPROVAL:
            next_status = (
                AgentRunStatus.RUNNING
                if status is ApprovalStatus.APPROVED
                else AgentRunStatus.FAILED
            )
            self.transition_run(agent_run_id=run.id, status=next_status)
        self.audit.record(
            event_type="approval.decided",
            summary=f"approval decided: {status}",
            subject_type="approval_request",
            subject_id=approval.id,
            actor_user_id=decided_by_user_id,
            agent_run_id=approval.agent_run_id,
        )
        self.session.flush()
        return approval

    def transition_task(self, *, task_id: str, status: TaskStatus) -> Task:
        task = self.tasks.get(task_id)
        if task is None:
            raise EntityNotFoundError(f"task not found: {task_id}")
        task.status = status
        self.audit.record(
            event_type="task.status_changed",
            summary=f"task status changed: {status}",
            subject_type="task",
            subject_id=task.id,
        )
        self.session.flush()
        return task

    def transition_step(self, *, step: AgentStep, status: AgentStepStatus) -> AgentStep:
        step.status = status
        now = datetime.now(UTC)
        if status is AgentStepStatus.RUNNING and step.started_at is None:
            step.started_at = now
        if status in {AgentStepStatus.COMPLETED, AgentStepStatus.FAILED, AgentStepStatus.SKIPPED}:
            step.completed_at = now
        self.session.flush()
        return step
