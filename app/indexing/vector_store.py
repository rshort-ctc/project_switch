import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.indexing.types import CodeChunk


@dataclass(frozen=True)
class VectorRecord:
    chunk: CodeChunk
    embedding: list[float]


@dataclass(frozen=True)
class VectorSearchResult:
    chunk: CodeChunk
    score: float


class VectorStore(Protocol):
    def upsert(self, records: list[VectorRecord]) -> None:
        pass

    def search(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        pass


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            self.records[record.chunk.id] = record

    def search(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        results = [
            VectorSearchResult(
                chunk=record.chunk, score=_cosine_similarity(embedding, record.embedding)
            )
            for record in self.records.values()
        ]
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


class QdrantVectorStore:
    def __init__(
        self, *, collection: str = "switch_code_chunks", endpoint: str | None = None
    ) -> None:
        settings = get_settings()
        self.collection = collection
        self.endpoint = (endpoint or str(settings.vector_store_url)).rstrip("/")
        self.client = httpx.Client(base_url=self.endpoint, timeout=30)

    def upsert(self, records: list[VectorRecord]) -> None:
        points = [
            {
                "id": record.chunk.id,
                "vector": record.embedding,
                "payload": {
                    "file_path": record.chunk.file_path,
                    "language": record.chunk.language,
                    "chunk_type": record.chunk.chunk_type.value,
                    "symbol_name": record.chunk.symbol_name,
                    "sha256": record.chunk.sha256,
                    "git_commit": record.chunk.git_commit,
                },
            }
            for record in records
        ]
        if points:
            self.client.put(
                f"/collections/{self.collection}/points", json={"points": points}
            ).raise_for_status()

    def search(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        _ = embedding
        _ = limit
        raise NotImplementedError(
            "Qdrant search requires chunk payload hydration and is not used in tests"
        )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
