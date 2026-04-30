from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app: str


class ServiceConfiguration(BaseModel):
    configured: bool


class HealthDetailsResponse(BaseModel):
    status: str
    app: str
    environment: str
    local_only: bool
    audit_retention_days: int
    default_permission_level: int
    sandbox_network_enabled: bool
    services: dict[str, ServiceConfiguration]
