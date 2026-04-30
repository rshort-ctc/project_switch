from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.health import HealthDetailsResponse, HealthResponse, ServiceConfiguration

router = APIRouter(tags=["health"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDependency) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@router.get("/health/details", response_model=HealthDetailsResponse)
def health_details(settings: SettingsDependency) -> HealthDetailsResponse:
    return HealthDetailsResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
        local_only=settings.local_only,
        audit_retention_days=settings.audit_retention_days,
        default_permission_level=settings.default_permission_level,
        sandbox_network_enabled=settings.sandbox_network_enabled,
        services={
            "postgres": ServiceConfiguration(configured=bool(settings.database_url)),
            "redis": ServiceConfiguration(configured=bool(settings.redis_url)),
            "vector_store": ServiceConfiguration(configured=bool(settings.vector_store_url)),
            "vllm": ServiceConfiguration(configured=bool(settings.vllm_endpoint)),
        },
    )
