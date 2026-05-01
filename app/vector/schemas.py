from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class VectorSourceKind(StrEnum):
    CODE = "code"
    DOCS = "docs"
    SYMBOL = "symbol"
    TEST = "test"
    CONFIG = "config"


@dataclass(frozen=True)
class CodeChunkPayload:
    repo_id: str
    repo_name: str
    file_path: str
    language: str
    commit_sha: str | None
    chunk_hash: str
    chunk_type: str
    symbol_name: str | None
    start_line: int
    end_line: int
    indexed_at: datetime
    text_preview: str
    source_kind: VectorSourceKind

    def to_qdrant_payload(self) -> dict[str, object]:
        return {
            "repo_id": self.repo_id,
            "repo_name": self.repo_name,
            "file_path": self.file_path,
            "language": self.language,
            "commit_sha": self.commit_sha,
            "chunk_hash": self.chunk_hash,
            "chunk_type": self.chunk_type,
            "symbol_name": self.symbol_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "indexed_at": self.indexed_at.astimezone(UTC).isoformat(),
            "text_preview": self.text_preview,
            "source_kind": self.source_kind.value,
        }


@dataclass(frozen=True)
class VectorPoint:
    id: str
    vector: list[float]
    payload: CodeChunkPayload


@dataclass(frozen=True)
class VectorSearchMatch:
    id: str
    score: float
    payload: dict[str, object]
