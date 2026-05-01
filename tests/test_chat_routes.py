import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes import chat as chat_routes
from app.core.config import Settings
from app.model_gateway.schemas import ChatCompletionResponse, ModelProvider
from app.schemas.cli_api import ChatMessageInput, ChatRequest

DEFAULT_CHAT_TEMPERATURE = 0.1
DEFAULT_CHAT_MAX_TOKENS = 450


def test_chat_request_defaults_to_chat_model_role() -> None:
    request = ChatRequest(messages=[ChatMessageInput(role="user", content="hello")])

    assert request.model_role == "chat_model"
    assert request.temperature == DEFAULT_CHAT_TEMPERATURE
    assert request.max_tokens == DEFAULT_CHAT_MAX_TOKENS


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


def test_degenerate_model_output_is_detected() -> None:
    repeated = " ".join(["Diagram"] * 50 + ["OPS"] * 20 + ["ade"] * 20)

    assert chat_routes._is_degenerate_model_output(repeated)
    assert not chat_routes._is_degenerate_model_output(
        "SWITCH is running, but the selected local model still needs a live smoke test."
    )


def test_chat_blocks_degenerate_model_output(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DegenerateGateway:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def chat_completion(self, request: object) -> ChatCompletionResponse:
            return ChatCompletionResponse(
                model="phi4-mini:latest",
                content=" ".join(["Criteria"] * 60 + ["Diagram"] * 25),
                finish_reason="length",
                completion_tokens=85,
            )

    monkeypatch.setattr(chat_routes, "LocalModelGateway", DegenerateGateway)

    response = chat_routes.chat(
        ChatRequest(
            messages=[
                ChatMessageInput(role="user", content="Are we fully operational?"),
            ],
            provider="ollama_local",
            model="phi4-mini:latest",
            max_bundles=0,
        ),
        session,
    )

    assert response.degraded
    assert not response.used_model
    assert response.stop_reason == "model output failed quality gate"
    assert "blocked" in response.answer
    assert response.model == "phi4-mini:latest"
