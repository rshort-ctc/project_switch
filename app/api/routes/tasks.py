import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.repositories import ValidationRunRepository
from app.db.session import get_db_session
from app.schemas.cli_api import (
    TaskApplyPatchRequest,
    TaskApplyPatchResponse,
    TaskCreateResponse,
    TaskDiffResponse,
    TaskListResponse,
    TaskLogsResponse,
    TaskRunRequest,
    TaskRunResponse,
    TaskStatusResponse,
    ValidationResultsResponse,
)
from app.schemas.durable import (
    AgentRunRead,
    AuditEventRead,
    TaskCreate,
    TaskRead,
    ValidationRunRead,
)
from app.security import PermissionLevel, PolicyConfig, PolicyEngine
from app.services.audit import AuditService
from app.services.exceptions import EntityNotFoundError
from app.services.runs import RunService
from app.services.workflow_runner import WorkflowRunnerService, run_workflow_background
from app.tools import ToolRegistry
from app.tools.schemas import ApplyPatchInput, ToolContext

router = APIRouter(prefix="/tasks", tags=["tasks"])

SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=TaskCreateResponse)
def create_task(request: TaskCreate, session: SessionDependency) -> TaskCreateResponse:
    service = RunService(session)
    repository = service.repositories.get(request.repository_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository not found")
    if service.users.get(request.created_by_user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    task = service.create_task(
        repository_id=request.repository_id,
        created_by_user_id=request.created_by_user_id,
        title=request.title,
        description=request.description,
    )
    run = service.create_agent_run(task_id=task.id, base_branch=repository.default_branch)
    session.commit()
    return TaskCreateResponse(
        task=TaskRead.model_validate(task),
        run=AgentRunRead.model_validate(run),
    )


@router.get("", response_model=TaskListResponse)
def list_tasks(session: SessionDependency) -> TaskListResponse:
    tasks = [TaskRead.model_validate(task) for task in RunService(session).tasks.list()]
    return TaskListResponse(tasks=tasks)


@router.get("/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str, session: SessionDependency) -> TaskStatusResponse:
    service = RunService(session)
    task = service.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    run = service.runs.latest_for_task(task_id)
    summary = WorkflowRunnerService(session).status_summary(task_id)
    return TaskStatusResponse(
        task=TaskRead.model_validate(task),
        run=AgentRunRead.model_validate(run) if run is not None else None,
        **summary,
    )


@router.post(
    "/{task_id}/run",
    response_model=TaskRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_task(
    task_id: str,
    request: TaskRunRequest,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
) -> TaskRunResponse:
    try:
        run = WorkflowRunnerService(session).prepare_run(
            task_id=task_id,
            actor_user_id=request.actor_user_id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    background_tasks.add_task(
        run_workflow_background,
        task_id=task_id,
        agent_run_id=run.id,
        actor_user_id=request.actor_user_id,
    )
    return TaskRunResponse(
        task_id=task_id,
        agent_run_id=run.id,
        status="queued",
        message="Agent workflow started.",
        status_url=f"/tasks/{task_id}",
    )


@router.get("/{task_id}/logs", response_model=TaskLogsResponse)
def task_logs(task_id: str, session: SessionDependency) -> TaskLogsResponse:
    service = RunService(session)
    task = service.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    run = service.runs.latest_for_task(task_id)
    events = (
        []
        if run is None
        else [
            AuditEventRead.model_validate(event)
            for event in AuditService(session).list_for_run(run.id)
        ]
    )
    return TaskLogsResponse(task_id=task_id, events=events)


@router.get("/{task_id}/diff", response_model=TaskDiffResponse)
def task_diff(task_id: str, session: SessionDependency) -> TaskDiffResponse:
    service = RunService(session)
    task = service.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    repository = service.repositories.get(task.repository_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository not found")

    repo_path = Path(repository.local_path)
    if not (repo_path / ".git").exists():
        return TaskDiffResponse(task_id=task_id, diff="", changed_files=[])

    diff = _git(repo_path, "diff")
    changed_output = _git(repo_path, "diff", "--name-only")
    changed_files = [line for line in changed_output.splitlines() if line]
    return TaskDiffResponse(task_id=task_id, diff=diff, changed_files=changed_files)


@router.post("/{task_id}/apply-approved-patch", response_model=TaskApplyPatchResponse)
def apply_approved_patch(
    task_id: str,
    request: TaskApplyPatchRequest,
    session: SessionDependency,
) -> TaskApplyPatchResponse:
    service = RunService(session)
    task = service.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    run = service.runs.latest_for_task(task_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent run not found")
    repository = service.repositories.get(task.repository_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository not found")
    if service.users.get(request.actor_user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    branch = request.branch or run.target_branch or f"switch/task-{task.id[:8]}"
    step = service.create_step(
        agent_run_id=run.id,
        sequence=1000,
        name="extension_apply_approved_patch",
    )
    tools = ToolRegistry(
        session=session,
        policy=PolicyEngine(
            PolicyConfig(
                workspace_path=Path(repository.local_path),
                permission_level=PermissionLevel.WRITE_WORKSPACE,
            ),
            session=session,
        ),
        context=ToolContext(
            agent_run_id=run.id,
            agent_step_id=step.id,
            workspace_path=Path(repository.local_path),
            actor_user_id=request.actor_user_id,
        ),
    )
    output = tools.apply_patch_to_workspace(
        ApplyPatchInput(
            path=Path("."),
            original_text="",
            replacement_text="",
            branch=branch,
            unified_diff=request.unified_diff,
            approval_request_id=request.approval_request_id,
            allow_binary=request.allow_binary,
        )
    )
    session.commit()
    return TaskApplyPatchResponse(
        task_id=task_id,
        success=output.success,
        changed_files=output.changed_files,
        added_files=output.added_files,
        deleted_files=output.deleted_files,
        patch_artifact_id=output.patch_artifact_id,
        rollback_artifact_id=output.rollback_artifact_id,
        approval_required=output.approval_required,
        error_code=output.error.code if output.error else None,
        error_message=output.error.message if output.error else None,
    )


@router.get("/{task_id}/validations", response_model=ValidationResultsResponse)
def validation_results(task_id: str, session: SessionDependency) -> ValidationResultsResponse:
    service = RunService(session)
    task = service.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    run = service.runs.latest_for_task(task_id)
    validations = (
        []
        if run is None
        else [
            ValidationRunRead.model_validate(validation)
            for validation in ValidationRunRepository(session).list_for_agent_run(run.id)
        ]
    )
    return ValidationResultsResponse(task_id=task_id, validations=validations)


def _git(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout
