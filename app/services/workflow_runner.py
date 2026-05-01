from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.workflow import (
    DeterministicCodingAgentWorkflow,
    WorkflowConfig,
    WorkflowInput,
    WorkflowState,
    WorkflowStatus,
)
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.indexing import InMemoryVectorStore, RepoIndexer
from app.indexing.embeddings import DeterministicEmbedder
from app.models.entities import AgentRun, AgentStep, ApprovalRequest, AuditEvent, Task, ToolCall
from app.models.enums import AgentRunStatus, ApprovalStatus, TaskStatus
from app.retrieval import RetrievalEngine
from app.security import PermissionLevel, PolicyConfig, PolicyEngine
from app.services.audit import AuditService
from app.services.exceptions import EntityNotFoundError
from app.services.runs import RunService


class WorkflowStatusSummary(TypedDict):
    current_state: str | None
    agent_step_count: int
    tool_call_count: int
    pending_approval_count: int
    latest_failure_message: str | None


class RuleBasedWorkflowModel:
    def complete(
        self,
        *,
        state: WorkflowState,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        if state is WorkflowState.CLASSIFY_TASK:
            return {"task_type": "coding_task", "summary": str(payload.get("task", ""))[:240]}
        if state is WorkflowState.DRAFT_PLAN:
            return {
                "plan": [
                    "Use retrieved repository context.",
                    "Stop for human approval before workspace mutation.",
                ]
            }
        if state is WorkflowState.RISK_ASSESSMENT:
            return {
                "risk": "medium",
                "approval_required": True,
                "reason": "Product workflow requires approval before mutation.",
            }
        if state is WorkflowState.REVIEW_DIFF:
            return {"summary": "diff review skipped until an approved mutation exists"}
        return {}


class WorkflowRunnerService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        model_factory: Callable[[], RuleBasedWorkflowModel] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.model_factory = model_factory or RuleBasedWorkflowModel
        self.runs = RunService(session)
        self.audit = AuditService(session)

    def prepare_run(self, *, task_id: str, actor_user_id: str | None = None) -> AgentRun:
        task = self._get_task(task_id)
        repository = self.runs.repositories.get(task.repository_id)
        if repository is None:
            raise EntityNotFoundError(f"repository not found for task: {task_id}")
        actor_id = actor_user_id or task.created_by_user_id
        if self.runs.users.get(actor_id) is None:
            raise EntityNotFoundError(f"user not found: {actor_id}")

        run = self.runs.runs.latest_for_task(task_id)
        if run is None or AgentRunStatus(run.status) in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            run = self.runs.create_agent_run(
                task_id=task.id,
                base_branch=repository.default_branch,
            )

        self.audit.record(
            event_type="workflow.queued",
            summary="workflow queued for background execution",
            subject_type="task",
            subject_id=task.id,
            actor_user_id=actor_id,
            agent_run_id=run.id,
        )
        self.session.flush()
        return run

    def run(self, *, task_id: str, agent_run_id: str, actor_user_id: str | None = None) -> None:
        task = self._get_task(task_id)
        run = self.runs.runs.get(agent_run_id)
        if run is None:
            raise EntityNotFoundError(f"agent run not found: {agent_run_id}")
        repository = self.runs.repositories.get(task.repository_id)
        if repository is None:
            raise EntityNotFoundError(f"repository not found for task: {task_id}")
        actor_id = actor_user_id or task.created_by_user_id
        if self.runs.users.get(actor_id) is None:
            raise EntityNotFoundError(f"user not found: {actor_id}")

        self.audit.record(
            event_type="workflow.started",
            summary="workflow started",
            subject_type="agent_run",
            subject_id=run.id,
            actor_user_id=actor_id,
            agent_run_id=run.id,
        )
        self.runs.transition_task(task_id=task.id, status=TaskStatus.RUNNING)
        self.session.commit()

        try:
            workflow = self._build_workflow(
                agent_run_id=run.id,
                actor_user_id=actor_id,
                workspace_path=Path(repository.local_path),
            )
            result = workflow.run(
                WorkflowInput(
                    task=_task_text(task),
                    base_branch=run.base_branch,
                )
            )
            final_task_status = _task_status_for_workflow(result.status)
            self.runs.transition_task(task_id=task.id, status=final_task_status)
            event_type = (
                "workflow.waiting_for_approval"
                if result.status is WorkflowStatus.WAITING_APPROVAL
                else "workflow.completed"
            )
            self.audit.record(
                event_type=event_type,
                summary=result.final_report.summary,
                subject_type="agent_run",
                subject_id=run.id,
                actor_user_id=actor_id,
                agent_run_id=run.id,
            )
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            self._mark_failed(task_id=task.id, agent_run_id=run.id, actor_user_id=actor_id, exc=exc)
            self.session.commit()
            raise

    def status_summary(self, task_id: str) -> WorkflowStatusSummary:
        self._get_task(task_id)
        run = self.runs.runs.latest_for_task(task_id)
        if run is None:
            return {
                "current_state": None,
                "agent_step_count": 0,
                "tool_call_count": 0,
                "pending_approval_count": 0,
                "latest_failure_message": None,
            }
        return {
            "current_state": self._latest_step_name(run.id),
            "agent_step_count": self._agent_step_count(run.id),
            "tool_call_count": self._tool_call_count(run.id),
            "pending_approval_count": self._pending_approval_count(run.id),
            "latest_failure_message": self._latest_failure_message(run.id),
        }

    def _build_workflow(
        self,
        *,
        agent_run_id: str,
        actor_user_id: str,
        workspace_path: Path,
    ) -> DeterministicCodingAgentWorkflow:
        indexer = RepoIndexer(embedder=DeterministicEmbedder(), vector_store=InMemoryVectorStore())
        snapshot = indexer.index(workspace_path)
        policy_level = PermissionLevel(self.settings.default_permission_level)
        policy = PolicyEngine(
            PolicyConfig(
                workspace_path=workspace_path,
                permission_level=policy_level,
                protected_branches=self.settings.protected_branches,
            ),
            session=self.session,
        )
        return DeterministicCodingAgentWorkflow(
            session=self.session,
            model=self.model_factory(),
            policy=policy,
            workspace_path=workspace_path,
            agent_run_id=agent_run_id,
            actor_user_id=actor_user_id,
            indexer=indexer,
            retrieval_engine=RetrievalEngine(indexer=indexer, snapshot=snapshot),
            config=WorkflowConfig(validation_command=None),
        )

    def _mark_failed(
        self,
        *,
        task_id: str,
        agent_run_id: str,
        actor_user_id: str,
        exc: Exception,
    ) -> None:
        run = self.runs.runs.get(agent_run_id)
        if run is not None and AgentRunStatus(run.status) in {
            AgentRunStatus.PENDING,
            AgentRunStatus.RUNNING,
            AgentRunStatus.WAITING_APPROVAL,
        }:
            if AgentRunStatus(run.status) is AgentRunStatus.PENDING:
                self.runs.transition_run(agent_run_id=agent_run_id, status=AgentRunStatus.RUNNING)
            self.runs.transition_run(agent_run_id=agent_run_id, status=AgentRunStatus.FAILED)
        self.runs.transition_task(task_id=task_id, status=TaskStatus.FAILED)
        self.audit.record(
            event_type="workflow.failed",
            summary=f"workflow failed: {exc}",
            subject_type="agent_run",
            subject_id=agent_run_id,
            actor_user_id=actor_user_id,
            agent_run_id=agent_run_id,
        )

    def _get_task(self, task_id: str) -> Task:
        task = self.runs.tasks.get(task_id)
        if task is None:
            raise EntityNotFoundError(f"task not found: {task_id}")
        return task

    def _latest_step_name(self, agent_run_id: str) -> str | None:
        statement = (
            select(AgentStep.name)
            .where(AgentStep.agent_run_id == agent_run_id)
            .order_by(AgentStep.sequence.desc(), AgentStep.created_at.desc())
            .limit(1)
        )
        return self.session.execute(statement).scalar_one_or_none()

    def _agent_step_count(self, agent_run_id: str) -> int:
        statement = (
            select(func.count())
            .select_from(AgentStep)
            .where(AgentStep.agent_run_id == agent_run_id)
        )
        return int(self.session.execute(statement).scalar_one())

    def _tool_call_count(self, agent_run_id: str) -> int:
        statement = (
            select(func.count())
            .select_from(ToolCall)
            .join(AgentStep)
            .where(AgentStep.agent_run_id == agent_run_id)
        )
        return int(self.session.execute(statement).scalar_one())

    def _pending_approval_count(self, agent_run_id: str) -> int:
        statement = (
            select(func.count())
            .select_from(ApprovalRequest)
            .where(
                ApprovalRequest.agent_run_id == agent_run_id,
                ApprovalRequest.status == ApprovalStatus.PENDING,
            )
        )
        return int(self.session.execute(statement).scalar_one())

    def _latest_failure_message(self, agent_run_id: str) -> str | None:
        failed_step = self.session.execute(
            select(AgentStep.summary)
            .where(AgentStep.agent_run_id == agent_run_id, AgentStep.status == "failed")
            .order_by(AgentStep.completed_at.desc(), AgentStep.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        if failed_step:
            return failed_step
        return self.session.execute(
            select(AuditEvent.summary)
            .where(
                AuditEvent.agent_run_id == agent_run_id,
                AuditEvent.event_type == "workflow.failed",
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(1)
        ).scalar_one_or_none()


def run_workflow_background(
    *,
    task_id: str,
    agent_run_id: str,
    actor_user_id: str | None,
    session_factory: sessionmaker[Session] = SessionLocal,
) -> None:
    with session_factory() as session:
        WorkflowRunnerService(session).run(
            task_id=task_id,
            agent_run_id=agent_run_id,
            actor_user_id=actor_user_id,
        )


def _task_text(task: Task) -> str:
    if task.description:
        return f"{task.title}\n\n{task.description}"
    return task.title


def _task_status_for_workflow(status: WorkflowStatus) -> TaskStatus:
    if status is WorkflowStatus.COMPLETED:
        return TaskStatus.COMPLETED
    if status is WorkflowStatus.WAITING_APPROVAL:
        return TaskStatus.WAITING_APPROVAL
    if status is WorkflowStatus.FAILED:
        return TaskStatus.FAILED
    return TaskStatus.RUNNING
