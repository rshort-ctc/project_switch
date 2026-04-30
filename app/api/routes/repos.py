from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.repositories import RepoIndexRepository
from app.db.session import get_db_session
from app.indexing import InMemoryVectorStore, RepoIndexer
from app.indexing.embeddings import DeterministicEmbedder
from app.models.entities import Repository
from app.models.enums import RepoIndexStatus
from app.schemas.cli_api import RepoIndexResponse, RepositoryListResponse, RepoStatusResponse
from app.schemas.durable import RepositoryCreate, RepositoryRead
from app.services.runs import RunService

router = APIRouter(prefix="/repos", tags=["repos"])

SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=RepositoryRead)
def add_repository(request: RepositoryCreate, session: SessionDependency) -> Repository:
    local_path = Path(request.local_path).expanduser()
    if not local_path.exists() or not local_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repository path is not a readable directory",
        )
    repository = RunService(session).register_repository(
        name=request.name,
        local_path=str(local_path.resolve()),
        default_branch=request.default_branch,
    )
    session.commit()
    return repository


@router.get("", response_model=RepositoryListResponse)
def list_repositories(session: SessionDependency) -> RepositoryListResponse:
    repositories = [
        RepositoryRead.model_validate(repository)
        for repository in RunService(session).repositories.list()
    ]
    return RepositoryListResponse(repositories=repositories)


@router.post("/{repository_id}/index", response_model=RepoIndexResponse)
def index_repository(repository_id: str, session: SessionDependency) -> RepoIndexResponse:
    service = RunService(session)
    repository = service.repositories.get(repository_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository not found")
    snapshot = RepoIndexer(
        embedder=DeterministicEmbedder(),
        vector_store=InMemoryVectorStore(),
    ).index(Path(repository.local_path))
    repo_index = RepoIndexRepository(session).create(
        repository_id=repository.id,
        commit_sha=snapshot.git_commit or "",
    )
    repo_index.status = RepoIndexStatus.READY
    repo_index.indexed_at = datetime.now(UTC)
    repo_index.exact_index_ready = True
    repo_index.symbol_index_ready = True
    repo_index.semantic_index_ready = True
    repo_index.git_metadata_ready = True
    session.commit()
    return _index_response(
        repository_id=repository.id,
        index_id=repo_index.id,
        status=str(repo_index.status),
        commit_sha=snapshot.git_commit or "",
        indexed_files=snapshot.status.indexed_files,
        indexed_chunks=snapshot.status.indexed_chunks,
        skipped_ignored_files=snapshot.status.skipped_ignored_files,
        skipped_binary_files=snapshot.status.skipped_binary_files,
        skipped_unchanged_files=snapshot.status.skipped_unchanged_files,
    )


@router.get("/{repository_id}/status", response_model=RepoStatusResponse)
def repository_status(repository_id: str, session: SessionDependency) -> RepoStatusResponse:
    service = RunService(session)
    repository = service.repositories.get(repository_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository not found")
    latest = RepoIndexRepository(session).latest_for_repository(repository_id)
    latest_response = None
    if latest is not None:
        latest_response = _index_response(
            repository_id=repository.id,
            index_id=latest.id,
            status=str(latest.status),
            commit_sha=latest.commit_sha,
        )
    return RepoStatusResponse(
        repository=RepositoryRead.model_validate(repository),
        latest_index=latest_response,
    )


def _index_response(
    *,
    repository_id: str,
    index_id: str,
    status: str,
    commit_sha: str,
    indexed_files: int = 0,
    indexed_chunks: int = 0,
    skipped_ignored_files: int = 0,
    skipped_binary_files: int = 0,
    skipped_unchanged_files: int = 0,
) -> RepoIndexResponse:
    return RepoIndexResponse(
        repository_id=repository_id,
        index_id=index_id,
        status=status,
        commit_sha=commit_sha,
        indexed_files=indexed_files,
        indexed_chunks=indexed_chunks,
        skipped_ignored_files=skipped_ignored_files,
        skipped_binary_files=skipped_binary_files,
        skipped_unchanged_files=skipped_unchanged_files,
    )
