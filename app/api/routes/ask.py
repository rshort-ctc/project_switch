from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.cli_api import AskRequest, AskResponse
from app.services.repo_qa import (
    RepoQAService,
    RepositoryNotFoundError,
    RepositoryNotIndexedError,
    RepositoryPathError,
    RetrievalUnavailableError,
)

router = APIRouter(prefix="/ask", tags=["ask"])

SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=AskResponse)
def ask_question(request: AskRequest, session: SessionDependency) -> AskResponse:
    try:
        result = RepoQAService(session).answer_question(
            repository_id=request.repository_id,
            question=request.question,
            max_bundles=request.max_bundles,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="repository not found",
        ) from exc
    except RepositoryNotIndexedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RepositoryPathError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repository path is not a readable directory",
        ) from exc
    except RetrievalUnavailableError as exc:
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    session.commit()
    return RepoQAService(session).to_ask_response(result)
