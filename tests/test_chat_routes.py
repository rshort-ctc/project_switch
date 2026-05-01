import pytest
from fastapi import HTTPException

from app.api.routes import chat as chat_routes
from app.core.config import Settings
from app.model_gateway.schemas import ModelProvider


def test_ollama_cloud_provider_blocked_in_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_routes, "get_settings", lambda: Settings(_env_file=None))

    with pytest.raises(HTTPException, match="Ollama cloud"):
        chat_routes._validate_model_selection("ollama_cloud", "gpt-oss:cloud")


def test_ollama_cloud_suffix_blocked_in_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_routes, "get_settings", lambda: Settings(_env_file=None))

    with pytest.raises(HTTPException, match="Ollama cloud"):
        chat_routes._validate_model_selection("ollama_local", "qwen3-coder:480b-cloud")


def test_ollama_cloud_provider_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_routes,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            local_only=False,
            allow_ollama_cloud_models=False,
        ),
    )

    with pytest.raises(HTTPException, match="Ollama cloud"):
        chat_routes._validate_model_selection("ollama_cloud", "gpt-oss:cloud")


def test_ollama_cloud_provider_allowed_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_routes,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            local_only=False,
            allow_ollama_cloud_models=True,
        ),
    )

    provider = chat_routes._validate_model_selection("ollama_cloud", "gpt-oss:cloud")

    assert provider is ModelProvider.OLLAMA_CLOUD
