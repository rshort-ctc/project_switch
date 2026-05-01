import subprocess
from pathlib import Path

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.tasks import run_task
from app.db.repositories import ApprovalRequestRepository
from app.models.entities import AgentStep, AuditEvent, ToolCall
from app.models.enums import AgentRunStatus, ApprovalStatus, TaskStatus
from app.schemas.cli_api import TaskRunRequest
from app.services.runs import RunService
from app.services.workflow_runner import WorkflowRunnerService


def test_run_task_endpoint_queues_workflow(session: Session, tmp_path: Path) -> None:
    task_id, _user_id = _create_task(session, tmp_path)
    background_tasks = BackgroundTasks()

    response = run_task(task_id, TaskRunRequest(), background_tasks, session)

    assert response.task_id == task_id
    assert response.agent_run_id
    assert response.status == "queued"
    assert response.status_url == f"/tasks/{task_id}"
    assert len(background_tasks.tasks) == 1


def test_workflow_runner_moves_task_to_waiting_approval(session: Session, tmp_path: Path) -> None:
    task_id, user_id = _create_task(session, tmp_path)
    runner = WorkflowRunnerService(session)
    run = runner.prepare_run(task_id=task_id, actor_user_id=user_id)
    session.commit()

    runner.run(task_id=task_id, agent_run_id=run.id, actor_user_id=user_id)

    service = RunService(session)
    task = service.tasks.get(task_id)
    updated_run = service.runs.get(run.id)
    assert task is not None
    assert updated_run is not None
    assert TaskStatus(task.status) is TaskStatus.WAITING_APPROVAL
    assert AgentRunStatus(updated_run.status) is AgentRunStatus.WAITING_APPROVAL


def test_workflow_runner_persists_steps_audit_tools_and_approval(
    session: Session,
    tmp_path: Path,
) -> None:
    task_id, user_id = _create_task(session, tmp_path)
    runner = WorkflowRunnerService(session)
    run = runner.prepare_run(task_id=task_id, actor_user_id=user_id)
    session.commit()

    runner.run(task_id=task_id, agent_run_id=run.id, actor_user_id=user_id)

    steps = (
        session.execute(select(AgentStep).where(AgentStep.agent_run_id == run.id)).scalars().all()
    )
    audits = (
        session.execute(select(AuditEvent).where(AuditEvent.agent_run_id == run.id)).scalars().all()
    )
    tool_calls = (
        session.execute(select(ToolCall).join(AgentStep).where(AgentStep.agent_run_id == run.id))
        .scalars()
        .all()
    )
    approvals = ApprovalRequestRepository(session).list_pending()

    assert steps
    assert {event.event_type for event in audits} >= {
        "workflow.queued",
        "workflow.started",
        "workflow.waiting_for_approval",
    }
    assert {call.tool_name for call in tool_calls} >= {"retrieve_context", "request_approval"}
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval.agent_run_id == run.id
    assert approval.requested_by_user_id == user_id
    assert approval.requested_action == "workspace_mutation"
    assert approval.risk_level == "high"
    assert ApprovalStatus(approval.status) is ApprovalStatus.PENDING


def test_workflow_runner_status_summary(session: Session, tmp_path: Path) -> None:
    task_id, user_id = _create_task(session, tmp_path)
    runner = WorkflowRunnerService(session)
    run = runner.prepare_run(task_id=task_id, actor_user_id=user_id)
    session.commit()
    runner.run(task_id=task_id, agent_run_id=run.id, actor_user_id=user_id)

    summary = runner.status_summary(task_id)

    assert summary["current_state"] == "final_report"
    assert summary["agent_step_count"] >= 1
    assert summary["tool_call_count"] >= 1
    assert summary["pending_approval_count"] == 1
    assert summary["latest_failure_message"] is None


def test_workflow_runner_marks_failed_and_audits_exception(
    session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id, user_id = _create_task(session, tmp_path)
    runner = WorkflowRunnerService(session)
    run = runner.prepare_run(task_id=task_id, actor_user_id=user_id)
    session.commit()

    def fail_build(*args: object, **kwargs: object) -> object:
        raise RuntimeError("model setup failed")

    monkeypatch.setattr(runner, "_build_workflow", fail_build)

    with pytest.raises(RuntimeError, match="model setup failed"):
        runner.run(task_id=task_id, agent_run_id=run.id, actor_user_id=user_id)

    service = RunService(session)
    failed_run = service.runs.get(run.id)
    task = service.tasks.get(task_id)
    assert failed_run is not None
    assert task is not None
    assert AgentRunStatus(failed_run.status) is AgentRunStatus.FAILED
    assert TaskStatus(task.status) is TaskStatus.FAILED
    events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.agent_run_id == run.id,
                AuditEvent.event_type == "workflow.failed",
            )
        )
        .scalars()
        .all()
    )
    assert events


def _create_task(session: Session, tmp_path: Path) -> tuple[str, str]:
    repo_path = _git_repo(tmp_path)
    service = RunService(session)
    user = service.create_user(email=f"{repo_path.name}@example.test", display_name="Task User")
    repository = service.register_repository(
        name=repo_path.name,
        local_path=str(repo_path),
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Fix greeting",
        description="Find greet and require approval before changing module.py",
    )
    service.create_agent_run(task_id=task.id, base_branch="main")
    session.commit()
    return task.id, user.id


def _git_repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "module.py").write_text(
        "def greet() -> str:\n    return 'hello'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "local@example.test"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Local User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True)
    return repo_path
