from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class ChunkType(StrEnum):
    MODULE = "module"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    EXPORT = "export"


class SourceKind(StrEnum):
    CODE = "code"
    DOCS = "docs"
    SYMBOL = "symbol"
    TEST = "test"
    CONFIG = "config"


class SymbolKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    EXPORT = "export"


@dataclass(frozen=True)
class FileMetadata:
    path: Path
    relative_path: str
    language: str
    sha256: str
    size_bytes: int
    modified_at: datetime
    git_commit: str | None


@dataclass(frozen=True)
class CodeSymbol:
    name: str
    kind: SymbolKind
    file_path: str
    language: str
    start_line: int
    end_line: int
    parent: str | None = None


@dataclass(frozen=True)
class CodeChunk:
    id: str
    file_path: str
    language: str
    chunk_type: ChunkType
    text: str
    sha256: str
    start_line: int
    end_line: int
    symbol_name: str | None = None
    git_commit: str | None = None
    repo_id: str | None = None
    repo_name: str | None = None
    source_kind: SourceKind = SourceKind.CODE


@dataclass(frozen=True)
class IndexedFile:
    metadata: FileMetadata
    symbols: list[CodeSymbol]
    imports: list[str]
    exports: list[str]
    chunks: list[CodeChunk]


@dataclass
class IndexStatus:
    indexed_files: int = 0
    skipped_unchanged_files: int = 0
    skipped_ignored_files: int = 0
    skipped_binary_files: int = 0
    indexed_chunks: int = 0
    embedded_chunks: int = 0


@dataclass
class RepoIndexSnapshot:
    repo_path: Path
    git_commit: str | None
    files: list[IndexedFile] = field(default_factory=list)
    status: IndexStatus = field(default_factory=IndexStatus)
