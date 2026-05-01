import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.model_gateway.errors import (
    ModelGatewayConnectionError,
    ModelGatewayResponseError,
    RerankingNotAvailableError,
)
from app.model_gateway.logging import summarize_messages, summarize_texts
from app.model_gateway.registry import ModelRegistry
from app.model_gateway.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelHealthResponse,
    ModelProvider,
    ModelRole,
    RerankRequest,
    RerankResponse,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    timeout_seconds: float
    max_retries: int
    backoff_seconds: float


class LocalModelGateway:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        provider: ModelProvider = ModelProvider.LOCAL_VLLM,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider
        self.registry = ModelRegistry(self.settings)
        self.retry_policy = RetryPolicy(
            timeout_seconds=self.settings.model_request_timeout_seconds,
            max_retries=self.settings.model_max_retries,
            backoff_seconds=self.settings.model_retry_backoff_seconds,
        )
        self._client = client or httpx.Client(
            base_url=self._base_url(),
            timeout=self.retry_policy.timeout_seconds,
        )

    def health(self) -> ModelHealthResponse:
        models = self.list_models()
        return ModelHealthResponse(
            status="ok",
            endpoint=self._base_url(),
            model_count=len(models),
            local_only=self.settings.local_only,
        )

    def list_models(self) -> list[str]:
        response = self._request("GET", "/models")
        models = response.get("data", [])
        if not isinstance(models, list):
            raise ModelGatewayResponseError("model health response did not include a model list")
        model_ids: list[str] = []
        for model in models:
            if isinstance(model, dict) and isinstance(model.get("id"), str):
                model_ids.append(model["id"])
        return model_ids

    def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        model = request.model_override or self.registry.model_for(request.role)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        logger.info(
            "model_chat_request",
            extra={
                "model_role": request.role.value,
                "model": model,
                **summarize_messages(request.messages),
            },
        )
        response = self._request("POST", "/chat/completions", json=payload)
        return self._parse_chat_response(response)

    def stream_chat_completion(self, request: ChatCompletionRequest) -> Iterator[str]:
        model = request.model_override or self.registry.model_for(request.role)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        logger.info(
            "model_chat_stream_request",
            extra={
                "model_role": request.role.value,
                "model": model,
                **summarize_messages(request.messages),
            },
        )
        with self._client.stream("POST", "/chat/completions", json=payload) as response:
            self._raise_for_status(response)
            for line in response.iter_lines():
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ").strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    content = delta.get("content")
                    if isinstance(content, str):
                        yield content

    def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = self.registry.model_for(ModelRole.EMBEDDING)
        logger.info(
            "model_embedding_request",
            extra={
                "model_role": request.role.value,
                "model": model,
                **summarize_texts(request.inputs),
            },
        )
        response = self._request(
            "POST",
            "/embeddings",
            json={"model": model, "input": request.inputs},
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise ModelGatewayResponseError("embedding response did not include data list")
        embeddings: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list):
                raise ModelGatewayResponseError("embedding response item did not include vector")
            embeddings.append([float(value) for value in embedding])

        usage = response.get("usage", {})
        return EmbeddingResponse(
            model=str(response.get("model", model)),
            embeddings=embeddings,
            prompt_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            total_tokens=usage.get("total_tokens") if isinstance(usage, dict) else None,
        )

    def rerank(self, request: RerankRequest) -> RerankResponse:
        model = self.registry.model_for(ModelRole.RERANKER)
        raise RerankingNotAvailableError(
            "reranking is not implemented for local model role "
            f"'{request.role.value}' using {model}"
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                response = self._client.request(method, path, **kwargs)
                self._raise_for_status(response)
                parsed = response.json()
                if not isinstance(parsed, dict):
                    raise ModelGatewayResponseError("model server returned a non-object response")
                return parsed
            except (httpx.HTTPError, ModelGatewayResponseError) as exc:
                last_error = exc
                if attempt >= self.retry_policy.max_retries:
                    break
                time.sleep(self.retry_policy.backoff_seconds)
        raise ModelGatewayConnectionError(
            f"model gateway request failed: {last_error}"
        ) from last_error

    def _base_url(self) -> str:
        if self.provider in {ModelProvider.OLLAMA_LOCAL, ModelProvider.OLLAMA_CLOUD}:
            return str(self.settings.ollama_endpoint)
        return str(self.settings.vllm_endpoint)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ModelGatewayResponseError(
                f"model server returned HTTP {exc.response.status_code}"
            ) from exc

    @staticmethod
    def _parse_chat_response(response: dict[str, Any]) -> ChatCompletionResponse:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelGatewayResponseError("chat response did not include choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise ModelGatewayResponseError("chat response choice was malformed")
        message = first.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ModelGatewayResponseError("chat response did not include message content")

        usage = response.get("usage", {})
        return ChatCompletionResponse(
            model=str(response.get("model", "")),
            content=message["content"],
            finish_reason=first.get("finish_reason"),
            prompt_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            completion_tokens=usage.get("completion_tokens") if isinstance(usage, dict) else None,
            total_tokens=usage.get("total_tokens") if isinstance(usage, dict) else None,
        )
