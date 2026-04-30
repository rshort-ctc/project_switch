import pytest
from pydantic import ValidationError

from app.core.config import Settings

PRODUCTION_AUDIT_RETENTION_DAYS = 365


def test_settings_default_to_local_only() -> None:
    settings = Settings()

    assert settings.local_only is True
    assert settings.endpoint_is_local(str(settings.vllm_endpoint))
    assert settings.endpoint_is_local(str(settings.vector_store_url))


def test_local_only_rejects_public_vllm_endpoint() -> None:
    with pytest.raises(ValidationError, match="vllm_endpoint"):
        Settings(vllm_endpoint="https://api.openai.com/v1")


def test_local_only_allows_configured_compose_service_hosts() -> None:
    settings = Settings(
        vector_store_url="http://qdrant:6333",
        vllm_endpoint="http://model-gateway:8001/v1",
    )

    assert settings.endpoint_is_local(str(settings.vector_store_url))
    assert settings.endpoint_is_local(str(settings.vllm_endpoint))


def test_public_endpoint_can_only_be_configured_when_local_only_is_disabled() -> None:
    settings = Settings(local_only=False, vllm_endpoint="https://internal.example.invalid/v1")

    assert settings.local_only is False
    assert str(settings.vllm_endpoint) == "https://internal.example.invalid/v1"


def test_requires_protected_branches() -> None:
    with pytest.raises(ValidationError, match="protected branch"):
        Settings(protected_branches=())


def test_hardening_defaults_are_conservative() -> None:
    settings = Settings()

    assert settings.audit_retention_days >= PRODUCTION_AUDIT_RETENTION_DAYS
    assert settings.default_permission_level <= 1
    assert settings.sandbox_network_enabled is False


def test_invalid_hardening_settings_are_rejected() -> None:
    with pytest.raises(ValidationError, match="audit retention"):
        Settings(audit_retention_days=7)
    with pytest.raises(ValidationError, match="default permission"):
        Settings(default_permission_level=6)
    with pytest.raises(ValidationError, match="allowed local hosts"):
        Settings(allowed_local_hosts=("qdrant",))
