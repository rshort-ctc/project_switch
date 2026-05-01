import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from app.core.config import get_settings
from app.indexing.types import ChunkType, CodeChunk, SourceKind
from app.vector import CODE_CHUNKS_COLLECTION, CodeChunkPayload, QdrantCodeChunkStore, VectorPoint
from app.vector.schemas import VectorSourceKind


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

    def delete_by_repo_id(self, repo_id: str) -> None:
        pass

    def delete_by_file_path(self, *, repo_id: str, file_path: str) -> None:
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

    def delete_by_repo_id(self, repo_id: str) -> None:
        self.records = {
            key: record for key, record in self.records.items() if record.chunk.repo_id != repo_id
        }

    def delete_by_file_path(self, *, repo_id: str, file_path: str) -> None:
        self.records = {
            key: record
            for key, record in self.records.items()
            if not (record.chunk.repo_id == repo_id and record.chunk.file_path == file_path)
        }


class QdrantVectorStore:
    def __init__(
        self,
        *,
        collection: str = CODE_CHUNKS_COLLECTION,
        endpoint: str | None = None,
        repo_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self.collection = collection
        self.endpoint = (endpoint or str(settings.vector_store_url)).rstrip("/")
        self.repo_id = repo_id
        self.client = QdrantCodeChunkStore(endpoint=self.endpoint, collection=collection)

    def upsert(self, records: list[VectorRecord]) -> None:
        points = [_vector_point(record) for record in records]
        self.client.upsert_vectors(points)

    def search(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        matches = self.client.semantic_search(embedding, limit=limit, repo_id=self.repo_id)
        results: list[VectorSearchResult] = []
        for match in matches:
            chunk = _chunk_from_payload(match.id, match.payload)
            if chunk is not None:
                results.append(VectorSearchResult(chunk=chunk, score=match.score))
        return results

    def delete_by_repo_id(self, repo_id: str) -> None:
        self.client.delete_by_repo_id(repo_id)

    def delete_by_file_path(self, *, repo_id: str, file_path: str) -> None:
        self.client.delete_by_file_path(repo_id=repo_id, file_path=file_path)


def _vector_point(record: VectorRecord) -> VectorPoint:
    chunk = record.chunk
    payload = CodeChunkPayload(
        repo_id=chunk.repo_id or "unregistered",
        repo_name=chunk.repo_name or "unregistered",
        file_path=chunk.file_path,
        language=chunk.language,
        commit_sha=chunk.git_commit,
        chunk_hash=chunk.sha256,
        chunk_type=chunk.chunk_type.value,
        symbol_name=chunk.symbol_name,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        indexed_at=datetime.now(UTC),
        text_preview=chunk.text[:500],
        source_kind=VectorSourceKind(chunk.source_kind.value),
    )
    return VectorPoint(
        id=str(uuid5(NAMESPACE_URL, chunk.id)),
        vector=record.embedding,
        payload=payload,
    )


def _chunk_from_payload(point_id: str, payload: dict[str, object]) -> CodeChunk | None:
    try:
        return CodeChunk(
            id=point_id,
            file_path=str(payload["file_path"]),
            language=str(payload["language"]),
            chunk_type=ChunkType(str(payload["chunk_type"])),
            text=str(payload.get("text_preview") or ""),
            sha256=str(payload["chunk_hash"]),
            start_line=_payload_int(payload["start_line"]),
            end_line=_payload_int(payload["end_line"]),
            symbol_name=(
                str(payload["symbol_name"]) if payload.get("symbol_name") is not None else None
            ),
            git_commit=str(payload["commit_sha"]) if payload.get("commit_sha") else None,
            repo_id=str(payload["repo_id"]) if payload.get("repo_id") else None,
            repo_name=str(payload["repo_name"]) if payload.get("repo_name") else None,
            source_kind=SourceKind(str(payload.get("source_kind") or "code")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _payload_int(value: object) -> int:
    if isinstance(value, int | str | bytes | bytearray):
        return int(value)
    raise TypeError("payload value is not integer-like")


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
