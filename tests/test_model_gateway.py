import json

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.model_gateway import LocalModelGateway, ModelRegistry
from app.model_gateway.errors import (
    ModelGatewayConnectionError,
    ModelGatewayResponseError,
    ModelNotConfiguredError,
    RerankingNotAvailableError,
)
from app.model_gateway.schemas import (
    ChatCompletionRequest,
    ChatMessage,
    EmbeddingRequest,
    ModelRole,
    RerankRequest,
)

HTTP_OK = 200
HTTP_INTERNAL_SERVER_ERROR = 500
CHAT_TOTAL_TOKENS = 5
EMBEDDING_TOTAL_TOKENS = 4
MODEL_COUNT = 2
RETRY_ATTEMPTS = 2


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "planner_model": "local-planner",
        "coder_model": "local-coder",
        "reviewer_model": "local-reviewer",
        "summarizer_model": "local-summarizer",
        "embedding_model": "local-embedder",
        "reranker_model": "local-reranker",
        "model_retry_backoff_seconds": 0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_gateway(
    handler: httpx.MockTransport, settings: Settings | None = None
) -> LocalModelGateway:
    active_settings = settings or make_settings()
    client = httpx.Client(transport=handler, base_url=str(active_settings.vllm_endpoint))
    return LocalModelGateway(settings=active_settings, client=client)


def test_model_registry_requires_configured_role() -> None:
    registry = ModelRegistry(Settings(_env_file=None))

    with pytest.raises(ModelNotConfiguredError, match="planner_model"):
        registry.model_for(ModelRole.PLANNER)


def test_local_only_rejects_remote_model_endpoint() -> None:
    with pytest.raises(ValidationError, match="vllm_endpoint"):
        Settings(vllm_endpoint="https://api.openai.com/v1")


def test_chat_completion_uses_openai_compatible_endpoint() -> None:
    seen_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        seen_payload.update(json.loads(request.content))
        return httpx.Response(
            HTTP_OK,
            json={
                "model": "local-planner",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Plan created."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": CHAT_TOTAL_TOKENS,
                },
            },
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    response = gateway.chat_completion(
        ChatCompletionRequest(
            role=ModelRole.PLANNER,
            messages=[ChatMessage(role="user", content="Plan the work")],
        )
    )

    assert seen_payload["model"] == "local-planner"
    assert seen_payload["stream"] is False
    assert response.content == "Plan created."
    assert response.total_tokens == CHAT_TOTAL_TOKENS


def test_embedding_request_returns_vectors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        payload = json.loads(request.content)
        assert payload["model"] == "local-embedder"
        return httpx.Response(
            HTTP_OK,
            json={
                "model": "local-embedder",
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
                "usage": {"prompt_tokens": 4, "total_tokens": EMBEDDING_TOTAL_TOKENS},
            },
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    response = gateway.embeddings(EmbeddingRequest(inputs=["repo context"]))

    assert response.model == "local-embedder"
    assert response.embeddings == [[0.1, 0.2, 0.3]]
    assert response.total_tokens == EMBEDDING_TOTAL_TOKENS


def test_streaming_chat_completion_yields_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        content = (
            'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(HTTP_OK, content=content.encode("utf-8"))

    gateway = make_gateway(httpx.MockTransport(handler))
    chunks = list(
        gateway.stream_chat_completion(
            ChatCompletionRequest(
                role=ModelRole.CODER,
                messages=[ChatMessage(role="user", content="Say hello")],
            )
        )
    )

    assert chunks == ["Hel", "lo"]


def test_health_checks_model_server() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(
            HTTP_OK, json={"data": [{"id": "local-planner"}, {"id": "local-coder"}]}
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    response = gateway.health()

    assert response.status == "ok"
    assert response.model_count == MODEL_COUNT
    assert response.local_only is True


def test_retry_policy_recovers_from_transient_failure() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(HTTP_INTERNAL_SERVER_ERROR, json={"error": "not ready"})
        return httpx.Response(HTTP_OK, json={"data": []})

    gateway = make_gateway(
        httpx.MockTransport(handler),
        settings=make_settings(model_max_retries=1),
    )

    assert gateway.health().status == "ok"
    assert attempts == RETRY_ATTEMPTS


def test_failures_return_useful_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(HTTP_OK, json={"choices": []})

    gateway = make_gateway(httpx.MockTransport(handler))

    with pytest.raises(ModelGatewayResponseError, match="choices"):
        gateway.chat_completion(
            ChatCompletionRequest(
                role=ModelRole.PLANNER,
                messages=[ChatMessage(role="user", content="Plan")],
            )
        )


def test_connection_failures_are_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    gateway = make_gateway(
        httpx.MockTransport(handler), settings=make_settings(model_max_retries=0)
    )

    with pytest.raises(ModelGatewayConnectionError, match="connection refused"):
        gateway.health()


def test_reranking_placeholder_is_explicit() -> None:
    gateway = make_gateway(httpx.MockTransport(lambda request: httpx.Response(HTTP_OK, json={})))

    with pytest.raises(RerankingNotAvailableError, match="not implemented"):
        gateway.rerank(RerankRequest(query="bug", documents=["a", "b"]))


def test_request_logging_does_not_include_prompt_content(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_prompt = "repo content token=super-secret"
    log_events: list[dict[str, object]] = []

    class CapturingLogger:
        def info(self, message: str, *, extra: dict[str, object]) -> None:
            log_events.append({"message": message, **extra})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            HTTP_OK,
            json={
                "model": "local-planner",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            },
        )

    gateway = make_gateway(httpx.MockTransport(handler))
    monkeypatch.setattr("app.model_gateway.client.logger", CapturingLogger())
    gateway.chat_completion(
        ChatCompletionRequest(
            role=ModelRole.PLANNER,
            messages=[ChatMessage(role="user", content=secret_prompt)],
        )
    )

    serialized_logs = json.dumps(log_events)
    assert "super-secret" not in serialized_logs
    assert "repo content" not in serialized_logs
    assert "content_fingerprint" in serialized_logs
