import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.api.routes.ask import ask_question
from app.api.routes.chat import chat
from app.api.routes.repos import add_repository, index_repository, repository_status
from app.api.routes.tasks import (
    apply_approved_patch,
    create_task,
    task_diff,
    task_logs,
    task_status,
    validation_results,
)
from app.models.enums import ApprovalStatus
from app.schemas.cli_api import AskRequest, ChatMessageInput, ChatRequest, TaskApplyPatchRequest
from app.schemas.durable import RepositoryCreate, TaskCreate
from app.services.runs import RunService


def test_repo_registration_index_and_status(session: Session, tmp_path: Path) -> None:
    repo_path = _sample_repo(tmp_path)

    repository = add_repository(
        RepositoryCreate(name="demo", local_path=str(repo_path), default_branch="main"),
        session,
    )
    index = index_repository(repository.id, session)
    status = repository_status(repository.id, session)

    assert repository.local_path == str(repo_path.resolve())
    assert index.status == "ready"
    assert index.indexed_files >= 1
    assert status.latest_index is not None
    assert status.latest_index.index_id == index.index_id


def test_ask_returns_context_with_provenance(session: Session, tmp_path: Path) -> None:
    repo_path = _sample_repo(tmp_path)
    repository = add_repository(
        RepositoryCreate(name="demo", local_path=str(repo_path), default_branch="main"),
        session,
    )

    response = ask_question(
        AskRequest(repository_id=repository.id, question="greet function", max_bundles=3),
        session,
    )

    assert response.question == "greet function"
    assert response.contexts
    assert response.contexts[0].path.endswith("module.py")


def test_chat_returns_retrieval_fallback_when_model_unavailable(
    session: Session, tmp_path: Path
) -> None:
    repo_path = _sample_repo(tmp_path)
    repository = add_repository(
        RepositoryCreate(name="demo", local_path=str(repo_path), default_branch="main"),
        session,
    )

    response = chat(
        ChatRequest(
            repository_id=repository.id,
            messages=[ChatMessageInput(role="user", content="Where is greet implemented?")],
            max_bundles=3,
        ),
        session,
    )

    assert response.degraded
    assert not response.used_model
    assert response.contexts
    assert "module.py" in response.answer


def test_task_status_logs_diff_and_validations(session: Session, tmp_path: Path) -> None:
    repo_path = _git_repo(tmp_path)
    service = RunService(session)
    user = service.create_user(email="local@example.test", display_name="Local User")
    repository = service.register_repository(
        name="demo",
        local_path=str(repo_path),
        default_branch="main",
    )
    session.commit()

    created = create_task(
        TaskCreate(
            repository_id=repository.id,
            created_by_user_id=user.id,
            title="Fix greeting",
            description="Make the greeting friendlier",
        ),
        session,
    )
    (repo_path / "module.py").write_text("def greet():\n    return 'hello there'\n")

    status = task_status(created.task.id, session)
    logs = task_logs(created.task.id, session)
    diff = task_diff(created.task.id, session)
    validations = validation_results(created.task.id, session)

    assert status.run is not None
    assert logs.events
    assert "module.py" in diff.changed_files
    assert validations.validations == []


def test_apply_approved_patch_uses_backend_policy_and_audit(
    session: Session, tmp_path: Path
) -> None:
    repo_path = _git_repo(tmp_path)
    service = RunService(session)
    user = service.create_user(email="apply@example.test", display_name="Apply User")
    repository = service.register_repository(
        name="demo",
        local_path=str(repo_path),
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Patch greeting",
        description="Patch through extension route",
    )
    run = service.create_agent_run(task_id=task.id, base_branch="main")
    approval = service.request_approval(
        agent_run_id=run.id,
        requested_by_user_id=user.id,
        requested_action="apply_patch",
        risk_level="medium",
        reason="extension patch apply",
    )
    service.decide_approval(
        approval_request_id=approval.id,
        decided_by_user_id=user.id,
        status=ApprovalStatus.APPROVED,
        decision_note="approved for test",
    )
    session.commit()

    original = (repo_path / "module.py").read_text()
    replacement = "def greet():\n    return 'hello there'\n"
    diff = "".join(
        __import__("difflib").unified_diff(
            original.splitlines(keepends=True),
            replacement.splitlines(keepends=True),
            fromfile="a/module.py",
            tofile="b/module.py",
        )
    )

    response = apply_approved_patch(
        task.id,
        TaskApplyPatchRequest(
            actor_user_id=user.id,
            approval_request_id=approval.id,
            unified_diff=diff,
        ),
        session,
    )

    assert response.success
    assert response.changed_files == ["module.py"]
    assert "hello there" in (repo_path / "module.py").read_text()


def test_apply_patch_requires_approval(session: Session, tmp_path: Path) -> None:
    repo_path = _git_repo(tmp_path)
    service = RunService(session)
    user = service.create_user(email="deny@example.test", display_name="Deny User")
    repository = service.register_repository(
        name="demo",
        local_path=str(repo_path),
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Patch greeting",
        description="Patch through extension route",
    )
    service.create_agent_run(task_id=task.id, base_branch="main")
    session.commit()

    response = apply_approved_patch(
        task.id,
        TaskApplyPatchRequest(
            actor_user_id=user.id,
            approval_request_id="missing",
            unified_diff="--- a/module.py\n+++ b/module.py\n",
        ),
        session,
    )

    assert not response.success
    assert response.error_code == "approval_required"


def _sample_repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "module.py").write_text("def greet():\n    return 'hello'\n")
    return repo_path


def _git_repo(tmp_path: Path) -> Path:
    repo_path = _sample_repo(tmp_path)
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
