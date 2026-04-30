from typing import Protocol

from app.model_gateway import LocalModelGateway
from app.model_gateway.schemas import EmbeddingRequest


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        pass


class LocalModelEmbedder:
    def __init__(self, gateway: LocalModelGateway | None = None) -> None:
        self.gateway = gateway or LocalModelGateway()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self.gateway.embeddings(EmbeddingRequest(inputs=texts)).embeddings


class DeterministicEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float(len(text) % 997),
                float(sum(ord(char) for char in text[:500]) % 997),
                float(text.count("\n") + 1),
            ]
            for text in texts
        ]
