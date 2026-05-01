from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.repositories import RepoIndexRepository
from app.model_gateway.errors import ModelGatewayConnectionError
from app.model_gateway.schemas import ChatCompletionResponse
from app.models.entities import AuditEvent, ModelCall
from app.services.repo_qa import RepoQAService, RetrievalUnavailableError
from app.services.runs import RunService
from app.vector import QdrantStoreError
from app.vector.schemas import VectorSearchMatch


def test_repo_qa_uses_qdrant_context_and_records_successful_model_call(
    session: Session, tmp_path: Path
) -> None:
    repository_id = _ready_repository(session, tmp_path)
    service = RepoQAService(
        session,
        settings=Settings(
            _env_file=None,
            summarizer_model="summary-model",
            embedding_model="embed-model",
        ),
        embedder=_FakeEmbedder(),
        qdrant_store=_FakeQdrantStore(repository_id),
        model_gateway=_SuccessfulGateway(),
    )

    result = service.answer_question(
        repository_id=repository_id,
        question="Where is approval handled?",
        max_bundles=2,
    )

    assert result.used_model
    assert not result.degraded
    assert "app/api/routes/approvals.py" in result.answer
    assert result.contexts[0].lanes == ["semantic"]

    model_calls = session.execute(select(ModelCall)).scalars().all()
    assert len(model_calls) == 1
    assert model_calls[0].status == "succeeded"
    assert model_calls[0].model_role == "summarizer_model"
    assert model_calls[0].request_metadata["repository_id"] == repository_id

    audit_events = session.execute(select(AuditEvent)).scalars().all()
    assert {event.event_type for event in audit_events} >= {"ask.started", "ask.completed"}


def test_repo_qa_degrades_and_records_failed_model_call(
    session: Session, tmp_path: Path
) -> None:
    repository_id = _ready_repository(session, tmp_path)
    service = RepoQAService(
        session,
        settings=Settings(
            _env_file=None,
            summarizer_model="summary-model",
            embedding_model="embed-model",
        ),
        embedder=_FakeEmbedder(),
        qdrant_store=_FakeQdrantStore(repository_id),
        model_gateway=_FailingGateway(),
    )

    result = service.answer_question(
        repository_id=repository_id,
        question="Where is approval handled?",
        max_bundles=2,
    )

    assert not result.used_model
    assert result.degraded
    assert result.degraded_reason == "model unavailable"

    model_call = session.execute(select(ModelCall)).scalars().one()
    assert model_call.status == "failed"
    assert model_call.request_metadata["degraded"] is True
    audit_events = session.execute(select(AuditEvent.event_type)).scalars().all()
    assert "ask.degraded" in audit_events


def test_repo_qa_qdrant_unavailable_does_not_fall_back_silently(
    session: Session, tmp_path: Path
) -> None:
    repository_id = _ready_repository(session, tmp_path)
    service = RepoQAService(
        session,
        settings=Settings(_env_file=None, embedding_model="embed-model"),
        embedder=_FakeEmbedder(),
        qdrant_store=_UnavailableQdrantStore(),
    )

    with pytest.raises(RetrievalUnavailableError) as exc_info:
        service.answer_question(
            repository_id=repository_id,
            question="Where is approval handled?",
            max_bundles=2,
        )

    assert "persistent semantic retrieval unavailable" in str(exc_info.value)


def _ready_repository(session: Session, tmp_path: Path) -> str:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "approvals.py").write_text("def approve_request():\n    return True\n")
    service = RunService(session)
    repository = service.register_repository(
        name="demo",
        local_path=str(repo_path),
        default_branch="main",
    )
    repo_index = RepoIndexRepository(session).create(
        repository_id=repository.id,
        commit_sha="abc123",
    )
    RepoIndexRepository(session).mark_ready(
        repo_index_id=repo_index.id,
        indexed_file_count=1,
        indexed_chunk_count=1,
        vector_collection="switch_code_chunks",
    )
    session.commit()
    return repository.id


class _FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeQdrantStore:
    def __init__(self, repository_id: str) -> None:
        self.repository_id = repository_id

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
        assert repo_id == self.repository_id
        return [
            VectorSearchMatch(
                id="chunk-1",
                score=0.94,
                payload={
                    "repo_id": self.repository_id,
                    "file_path": "approvals.py",
                    "language": "python",
                    "commit_sha": "abc123",
                    "chunk_hash": "hash",
                    "chunk_type": "function",
                    "symbol_name": "approve_request",
                    "start_line": 1,
                    "end_line": 2,
                    "source_kind": "code",
                    "text_preview": "def approve_request(): ...",
                },
            )
        ][:limit]


class _UnavailableQdrantStore:
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
        raise QdrantStoreError("qdrant offline")


class _SuccessfulGateway:
    def chat_completion(self, request: object) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            model="summary-model",
            content="Approval handling is in app/api/routes/approvals.py:1-2.",
            finish_reason="stop",
            prompt_tokens=25,
            completion_tokens=12,
            total_tokens=37,
        )


class _FailingGateway:
    def chat_completion(self, request: object) -> ChatCompletionResponse:
        raise ModelGatewayConnectionError("gateway offline")
