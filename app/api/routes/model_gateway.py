from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import Settings, get_settings
from app.model_gateway import LocalModelGateway
from app.model_gateway.errors import ModelGatewayError
from app.model_gateway.schemas import ModelHealthResponse, ModelListResponse, ModelProvider
from app.schemas.cli_api import ModelCatalogResponse

router = APIRouter(prefix="/model-gateway", tags=["model-gateway"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]
ModelProviderQuery = Annotated[ModelProvider, Query()]


@router.get("/health", response_model=ModelHealthResponse)
def model_gateway_health(
    settings: SettingsDependency,
    provider: ModelProviderQuery = ModelProvider.LOCAL_VLLM,
) -> ModelHealthResponse:
    try:
        return LocalModelGateway(settings=settings, provider=provider).health()
    except ModelGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/models", response_model=ModelListResponse)
def model_gateway_models(
    settings: SettingsDependency,
    provider: ModelProviderQuery = ModelProvider.LOCAL_VLLM,
) -> ModelListResponse:
    try:
        return ModelListResponse(
            models=LocalModelGateway(settings=settings, provider=provider).list_models()
        )
    except ModelGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/catalog", response_model=ModelCatalogResponse)
def model_gateway_catalog(settings: SettingsDependency) -> ModelCatalogResponse:
    models_by_provider: dict[str, list[str]] = {}
    for provider in (ModelProvider.LOCAL_VLLM, ModelProvider.OLLAMA_LOCAL):
        try:
            models = LocalModelGateway(
                settings=settings,
                provider=provider,
            ).list_models()
            if settings.local_only or not settings.allow_ollama_cloud_models:
                models = [model for model in models if not _is_cloud_model(model)]
            models_by_provider[provider.value] = models
        except ModelGatewayError:
            models_by_provider[provider.value] = []
    if settings.allow_ollama_cloud_models and not settings.local_only:
        models_by_provider[ModelProvider.OLLAMA_CLOUD.value] = models_by_provider[
            ModelProvider.OLLAMA_LOCAL.value
        ]
    else:
        models_by_provider[ModelProvider.OLLAMA_CLOUD.value] = []
    models = sorted({model for values in models_by_provider.values() for model in values})
    return ModelCatalogResponse(
        providers=[provider.value for provider in ModelProvider],
        models=models,
        models_by_provider=models_by_provider,
        allow_ollama_cloud_models=settings.allow_ollama_cloud_models,
        local_only=settings.local_only,
    )


def _is_cloud_model(model: str) -> bool:
    return model.endswith(":cloud") or model.endswith("-cloud")
