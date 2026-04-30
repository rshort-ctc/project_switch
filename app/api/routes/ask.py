from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.indexing import InMemoryVectorStore, RepoIndexer
from app.indexing.embeddings import DeterministicEmbedder
from app.retrieval.engine import RetrievalEngine
from app.retrieval.types import RetrievalQuery
from app.schemas.cli_api import AskContext, AskRequest, AskResponse
from app.services.runs import RunService

router = APIRouter(prefix="/ask", tags=["ask"])

SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=AskResponse)
def ask_question(request: AskRequest, session: SessionDependency) -> AskResponse:
    repository = RunService(session).repositories.get(request.repository_id)
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repository not found")

    repo_path = Path(repository.local_path)
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repository path is not a readable directory",
        )

    indexer = RepoIndexer(
        embedder=DeterministicEmbedder(),
        vector_store=InMemoryVectorStore(),
    )
    snapshot = indexer.index(repo_path)
    result = RetrievalEngine(indexer=indexer, snapshot=snapshot).retrieve(
        RetrievalQuery(task=request.question, max_bundles=request.max_bundles)
    )

    contexts = [
        AskContext(
            path=bundle.citation.file_path,
            start_line=bundle.citation.start_line,
            end_line=bundle.citation.end_line,
            score=bundle.score,
            reasons=list(bundle.reasons),
        )
        for bundle in result.bundles
    ]
    answer = f"Found {len(contexts)} relevant context bundle(s) for the question."
    return AskResponse(question=request.question, answer=answer, contexts=contexts)
