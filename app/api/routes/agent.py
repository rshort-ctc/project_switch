from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.cli_api import AgentModelsResponse

router = APIRouter(prefix="/agent", tags=["agent"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/models", response_model=AgentModelsResponse)
def models(settings: SettingsDependency) -> AgentModelsResponse:
    return AgentModelsResponse(
        planner_model=settings.planner_model,
        coder_model=settings.coder_model,
        reviewer_model=settings.reviewer_model,
        summarizer_model=settings.summarizer_model,
        embedding_model=settings.embedding_model,
        reranker_model=settings.reranker_model,
    )
