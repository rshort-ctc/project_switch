from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.model_gateway import LocalModelGateway
from app.model_gateway.errors import ModelGatewayError
from app.model_gateway.schemas import ModelHealthResponse

router = APIRouter(prefix="/model-gateway", tags=["model-gateway"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/health", response_model=ModelHealthResponse)
def model_gateway_health(settings: SettingsDependency) -> ModelHealthResponse:
    try:
        return LocalModelGateway(settings=settings).health()
    except ModelGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
