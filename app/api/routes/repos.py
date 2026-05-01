from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.repositories import RepoIndexRepository
from app.db.session import get_db_session
from app.indexing import PersistentRepoIndexer, QdrantVectorStore
from app.indexing.embeddings import LocalModelEmbedder
from app.model_gateway.errors import ModelGatewayError
from app.models.entities import Repository
from app.schemas.cli_api import RepoIndexResponse, RepositoryListResponse, RepoStatusResponse
from app.schemas.durable import RepositoryCreate, RepositoryRead
from app.services.runs import RunService
from app.vector import CODE_CHUNKS_COLLECTION, QdrantStoreError

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
    resolved_path = str(local_path.resolve())
    service = RunService(session)
    existing_repository = service.repositories.get_by_local_path(resolved_path)
    if existing_repository is not None:
        return existing_repository
    repository = service.register_repository(
        name=request.name,
        local_path=resolved_path,
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
    repo_path = Path(repository.local_path)
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repository path is not a readable directory",
        )
    try:
        vector_store = QdrantVectorStore(collection=CODE_CHUNKS_COLLECTION, repo_id=repository.id)
        vector_store.delete_by_repo_id(repository.id)
        snapshot = PersistentRepoIndexer(
            session=session,
            repository_id=repository.id,
            repository_name=repository.name,
            embedder=LocalModelEmbedder(),
            vector_store=vector_store,
            vector_collection=CODE_CHUNKS_COLLECTION,
        ).index(repo_path)
    except (ModelGatewayError, QdrantStoreError, RuntimeError, ValueError) as exc:
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"repository indexing failed: {exc}",
        ) from exc
    latest = RepoIndexRepository(session).latest_for_repository(repository.id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="repository indexing did not create an index record",
        )
    session.commit()
    return _index_response(
        repository_id=repository.id,
        index_id=latest.id,
        status=str(latest.status),
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
