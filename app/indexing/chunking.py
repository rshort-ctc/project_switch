import hashlib
from pathlib import Path

from app.indexing.types import (
    ChunkType,
    CodeChunk,
    CodeSymbol,
    FileMetadata,
    SourceKind,
    SymbolKind,
)


def chunk_file(*, metadata: FileMetadata, text: str, symbols: list[CodeSymbol]) -> list[CodeChunk]:
    lines = text.splitlines()
    chunks: list[CodeChunk] = []
    covered: set[int] = set()
    for symbol in symbols:
        start = max(symbol.start_line, 1)
        end = min(symbol.end_line, len(lines))
        if start > end:
            continue
        chunk_text = "\n".join(lines[start - 1 : end])
        chunks.append(
            _make_chunk(
                metadata=metadata,
                text=chunk_text,
                chunk_type=_chunk_type_for_symbol(symbol),
                start_line=start,
                end_line=end,
                symbol_name=symbol.name,
            )
        )
        covered.update(range(start, end + 1))

    module_lines = [line for index, line in enumerate(lines, start=1) if index not in covered]
    module_text = "\n".join(line for line in module_lines if line.strip())
    if module_text:
        chunks.append(
            _make_chunk(
                metadata=metadata,
                text=module_text,
                chunk_type=ChunkType.MODULE,
                start_line=1,
                end_line=len(lines),
                symbol_name=None,
            )
        )
    if not chunks and text.strip():
        chunks.append(
            _make_chunk(
                metadata=metadata,
                text=text,
                chunk_type=ChunkType.MODULE,
                start_line=1,
                end_line=max(len(lines), 1),
                symbol_name=None,
            )
        )
    return chunks


def _chunk_type_for_symbol(symbol: CodeSymbol) -> ChunkType:
    if symbol.kind is SymbolKind.CLASS:
        return ChunkType.CLASS
    if symbol.kind is SymbolKind.METHOD:
        return ChunkType.METHOD
    if symbol.kind is SymbolKind.EXPORT:
        return ChunkType.EXPORT
    return ChunkType.FUNCTION


def _make_chunk(
    *,
    metadata: FileMetadata,
    text: str,
    chunk_type: ChunkType,
    start_line: int,
    end_line: int,
    symbol_name: str | None,
) -> CodeChunk:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    chunk_id = f"{metadata.relative_path}:{start_line}:{end_line}:{digest[:12]}"
    return CodeChunk(
        id=chunk_id,
        file_path=metadata.relative_path,
        language=metadata.language,
        chunk_type=chunk_type,
        text=text,
        sha256=digest,
        start_line=start_line,
        end_line=end_line,
        symbol_name=symbol_name,
        git_commit=metadata.git_commit,
        source_kind=_source_kind(metadata.relative_path, chunk_type),
    )


def _source_kind(relative_path: str, chunk_type: ChunkType) -> SourceKind:
    path = relative_path.lower()
    if chunk_type is not ChunkType.MODULE:
        return SourceKind.SYMBOL
    if (
        path.startswith(("tests/", "test/"))
        or "/tests/" in path
        or Path(path).name.startswith("test_")
    ):
        return SourceKind.TEST
    if path.endswith((".md", ".mdx", ".rst", ".txt")) or path.startswith("docs/"):
        return SourceKind.DOCS
    if Path(path).name in {"pyproject.toml", "package.json", "docker-compose.yml"}:
        return SourceKind.CONFIG
    return SourceKind.CODE
