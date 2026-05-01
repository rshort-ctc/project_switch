from functools import lru_cache
from ipaddress import ip_address, ip_network
from typing import Literal
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
MIN_AUDIT_RETENTION_DAYS = 30
MAX_DEFAULT_PERMISSION_LEVEL = 5


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SWITCH_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SWITCH"
    environment: Environment = "development"
    local_only: bool = True
    log_level: LogLevel = "INFO"
    log_json: bool = True

    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str | None = "/openapi.json"

    database_url: str = "postgresql+psycopg://switch:switch@localhost:55632/switch"
    redis_url: str = "redis://localhost:55637/0"
    vector_store_url: AnyHttpUrl = "http://localhost:55633"  # type: ignore[assignment]
    vllm_endpoint: AnyHttpUrl = "http://localhost:55680/v1"  # type: ignore[assignment]
    ollama_endpoint: AnyHttpUrl = "http://localhost:55681/v1"  # type: ignore[assignment]
    artifact_root: str = ".switch/artifacts"
    workspace_root: str = "./workspaces"
    courthouse_enabled: bool = True
    courthouse_context_default_exposure: Literal[
        "private_internal",
        "user_visible",
        "tool_safe",
        "repo_safe",
        "public_safe",
        "never_export",
    ] = "tool_safe"
    model_request_timeout_seconds: float = 30.0
    model_max_retries: int = 2
    model_retry_backoff_seconds: float = 0.2
    allow_ollama_cloud_models: bool = False
    sandbox_engine: Literal["auto", "docker", "podman"] = "auto"
    sandbox_image: str = "python:3.12-slim"
    sandbox_cpu_count: float = 1.0
    sandbox_memory: str = "1g"
    sandbox_timeout_seconds: int = 60
    sandbox_disk: str = "1g"
    sandbox_network_enabled: bool = False
    audit_retention_days: int = 365
    admin_contact: str = "local-admin@example.invalid"
    default_permission_level: int = 1

    planner_model: str | None = None
    coder_model: str | None = None
    reviewer_model: str | None = None
    summarizer_model: str | None = None
    embedding_model: str | None = None
    reranker_model: str | None = None

    protected_branches: tuple[str, ...] = ("main", "master", "release", "production")
    allowed_repo_roots: tuple[str, ...] = ("./workspaces",)
    allowed_network_cidrs: tuple[str, ...] = (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
    )
    allowed_local_hosts: tuple[str, ...] = (
        "localhost",
        "backend",
        "dashboard",
        "postgres",
        "redis",
        "qdrant",
        "model-gateway",
        "switch-api",
        "switch-web",
        "switch-db",
        "switch-redis",
        "switch-qdrant",
        "switch-vllm",
        "host.docker.internal",
    )

    @field_validator("allowed_network_cidrs")
    @classmethod
    def validate_cidrs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for cidr in value:
            ip_network(cidr)
        return value

    @field_validator("allowed_local_hosts")
    @classmethod
    def validate_allowed_local_hosts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(host.strip().lower() for host in value if host.strip())
        if "localhost" not in cleaned:
            raise ValueError("allowed local hosts must include localhost")
        return cleaned

    @field_validator("protected_branches")
    @classmethod
    def validate_protected_branches(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(branch.strip() for branch in value if branch.strip())
        if not cleaned:
            raise ValueError("at least one protected branch must be configured")
        return cleaned

    @field_validator("allowed_repo_roots")
    @classmethod
    def validate_allowed_repo_roots(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(root.strip() for root in value if root.strip())
        if not cleaned:
            raise ValueError("at least one allowed repo root must be configured")
        return cleaned

    @field_validator("model_request_timeout_seconds")
    @classmethod
    def validate_model_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("model request timeout must be greater than zero")
        return value

    @field_validator("model_max_retries")
    @classmethod
    def validate_model_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("model max retries cannot be negative")
        return value

    @field_validator("model_retry_backoff_seconds")
    @classmethod
    def validate_model_backoff(cls, value: float) -> float:
        if value < 0:
            raise ValueError("model retry backoff cannot be negative")
        return value

    @field_validator("sandbox_cpu_count")
    @classmethod
    def validate_sandbox_cpu_count(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("sandbox CPU count must be greater than zero")
        return value

    @field_validator("sandbox_timeout_seconds")
    @classmethod
    def validate_sandbox_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("sandbox timeout must be greater than zero")
        return value

    @field_validator("audit_retention_days")
    @classmethod
    def validate_audit_retention_days(cls, value: int) -> int:
        if value < MIN_AUDIT_RETENTION_DAYS:
            raise ValueError("audit retention must be at least 30 days")
        return value

    @field_validator("default_permission_level")
    @classmethod
    def validate_default_permission_level(cls, value: int) -> int:
        if value < 0 or value > MAX_DEFAULT_PERMISSION_LEVEL:
            raise ValueError("default permission level must be between 0 and 5")
        return value

    @model_validator(mode="after")
    def validate_local_only_endpoints(self) -> "Settings":
        if not self.local_only:
            return self

        for name, endpoint in {
            "vector_store_url": str(self.vector_store_url),
            "vllm_endpoint": str(self.vllm_endpoint),
            "ollama_endpoint": str(self.ollama_endpoint),
        }.items():
            if not self.endpoint_is_local(endpoint):
                raise ValueError(f"{name} must point to localhost or an approved local network")

        return self

    def endpoint_is_local(self, endpoint: str) -> bool:
        parsed = urlparse(endpoint)
        host = parsed.hostname
        if host is None:
            return False
        return self.host_is_local(host)

    def host_is_local(self, host: str) -> bool:
        if host.lower() in self.allowed_local_hosts:
            return True
        try:
            parsed = ip_address(host)
        except ValueError:
            return False
        return any(parsed in ip_network(cidr) for cidr in self.allowed_network_cidrs)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
