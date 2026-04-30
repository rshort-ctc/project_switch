from fastapi.testclient import TestClient

from app.main import create_app

HTTP_OK = 200
PRODUCTION_AUDIT_RETENTION_DAYS = 365


def test_health() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == HTTP_OK
    assert response.json() == {"status": "ok", "app": "SWITCH"}


def test_health_details() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/details")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["status"] == "ok"
    assert body["local_only"] is True
    assert body["audit_retention_days"] >= PRODUCTION_AUDIT_RETENTION_DAYS
    assert body["default_permission_level"] <= 1
    assert body["sandbox_network_enabled"] is False
    assert body["services"]["postgres"]["configured"] is True
    assert body["services"]["redis"]["configured"] is True
    assert body["services"]["vector_store"]["configured"] is True
    assert body["services"]["vllm"]["configured"] is True


def test_version() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/version")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["version"] == "0.1.0"
    assert isinstance(body["python"], str)
