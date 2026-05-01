import inspect
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes import repos as repo_routes
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
from app.db.repositories import RepoIndexRepository
from app.indexing import InMemoryVectorStore
from app.models.enums import ApprovalStatus
from app.schemas.cli_api import AskRequest, ChatMessageInput, ChatRequest, TaskApplyPatchRequest
from app.schemas.durable import RepositoryCreate, TaskCreate
from app.services.runs import RunService
from app.vector.schemas import VectorSearchMatch


def test_repo_registration_index_and_status(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = _sample_repo(tmp_path)
    _patch_persistent_indexing(monkeypatch)

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


def test_repo_registration_is_idempotent_by_resolved_path(
    session: Session, tmp_path: Path
) -> None:
    repo_path = _sample_repo(tmp_path)

    first = add_repository(
        RepositoryCreate(name="demo", local_path=str(repo_path), default_branch="main"),
        session,
    )
    second = add_repository(
        RepositoryCreate(name="demo-copy", local_path=str(repo_path / "."), default_branch="main"),
        session,
    )

    assert second.id == first.id
    assert second.local_path == str(repo_path.resolve())


def test_ask_returns_409_when_repo_has_no_ready_index(session: Session, tmp_path: Path) -> None:
    repo_path = _sample_repo(tmp_path)
    repository = add_repository(
        RepositoryCreate(name="demo", local_path=str(repo_path), default_branch="main"),
        session,
    )

    with pytest.raises(HTTPException) as exc_info:
        ask_question(
            AskRequest(repository_id=repository.id, question="greet function", max_bundles=3),
            session,
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "switch repo index" in str(exc_info.value.detail)


def test_ask_route_does_not_construct_test_indexing_backends() -> None:
    source = inspect.getsource(ask_question)

    assert "DeterministicEmbedder" not in source
    assert "InMemoryVectorStore" not in source


def test_ask_returns_context_with_provenance(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = _sample_repo(tmp_path)
    repository = add_repository(
        RepositoryCreate(name="demo", local_path=str(repo_path), default_branch="main"),
        session,
    )
    _mark_ready_index(session, repository.id)
    _patch_repo_qa_retrieval(monkeypatch, repository.id)

    response = ask_question(
        AskRequest(repository_id=repository.id, question="greet function", max_bundles=3),
        session,
    )

    assert response.question == "greet function"
    assert response.contexts
    assert response.contexts[0].path.endswith("module.py")
    assert response.contexts[0].lanes == ["semantic"]
    assert not response.used_model
    assert response.degraded
    assert response.degraded_reason in {"model not configured", "model unavailable"}
    assert response.index_id is not None
    assert response.retrieval_summary is not None
    assert "semantic" in response.retrieval_summary.lanes_used


def test_chat_returns_retrieval_fallback_when_model_unavailable(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = _sample_repo(tmp_path)
    repository = add_repository(
        RepositoryCreate(name="demo", local_path=str(repo_path), default_branch="main"),
        session,
    )
    _mark_ready_index(session, repository.id)
    _patch_repo_qa_retrieval(monkeypatch, repository.id)

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


def _mark_ready_index(session: Session, repository_id: str) -> None:
    repo_indexes = RepoIndexRepository(session)
    repo_index = repo_indexes.create(repository_id=repository_id, commit_sha="abc123")
    repo_indexes.mark_ready(
        repo_index_id=repo_index.id,
        indexed_file_count=1,
        indexed_chunk_count=1,
        vector_collection="switch_code_chunks",
    )
    session.commit()


def _patch_persistent_indexing(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

    class FakeVectorStore(InMemoryVectorStore):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__()

    monkeypatch.setattr(repo_routes, "LocalModelEmbedder", FakeEmbedder)
    monkeypatch.setattr(repo_routes, "QdrantVectorStore", FakeVectorStore)


def _patch_repo_qa_retrieval(monkeypatch: pytest.MonkeyPatch, repository_id: str) -> None:
    class FakeEmbedder:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in texts]

    class FakeQdrantStore:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def semantic_search(
            self,
            query_vector: list[float],
            *,
            limit: int,
            repo_id: str | None = None,
            language: str | None = None,
            file_path: str | None = None,
            symbol_name: str | None = None,
            chunk_type: str | None = None,
        ) -> list[VectorSearchMatch]:
            assert repo_id == repository_id
            return [
                VectorSearchMatch(
                    id="chunk-1",
                    score=0.91,
                    payload={
                        "repo_id": repository_id,
                        "file_path": "module.py",
                        "language": "python",
                        "commit_sha": "abc123",
                        "chunk_hash": "hash",
                        "chunk_type": "function",
                        "symbol_name": "greet",
                        "start_line": 1,
                        "end_line": 2,
                        "source_kind": "code",
                        "text_preview": "def greet(): ...",
                    },
                )
            ][:limit]

    monkeypatch.setattr("app.services.repo_qa.LocalModelEmbedder", FakeEmbedder)
    monkeypatch.setattr("app.services.repo_qa.QdrantCodeChunkStore", FakeQdrantStore)


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
