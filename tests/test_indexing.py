import subprocess
from pathlib import Path

from app.indexing import InMemoryVectorStore, RepoIndexer

INDEXED_CODE_FILES = 2
MIN_IGNORED_FILES = 2


class KeywordEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [_embed_text(text) for text in texts]


def _embed_text(text: str) -> list[float]:
    lowered = text.lower()
    return [
        float("authenticate" in lowered or "authentication" in lowered),
        float("widget" in lowered),
        float("hello" in lowered),
        float(len(lowered.split())),
    ]


def create_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.py\n*.log\n", encoding="utf-8")
    (repo / "app.py").write_text(
        "\n".join(
            [
                "import os",
                "",
                "class Widget:",
                "    def render(self) -> str:",
                "        return 'hello widget'",
                "",
                "def authenticate_user(token: str) -> bool:",
                "    return bool(token)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "frontend.ts").write_text(
        "\n".join(
            [
                "import { x } from './x'",
                "export function makeWidget() {",
                "  return 'widget'",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "ignored.py").write_text("def ignored(): pass\n", encoding="utf-8")
    (repo / "secret.txt").write_text("token=super-secret\n", encoding="utf-8")
    vendor = repo / "node_modules" / "package"
    vendor.mkdir(parents=True)
    (vendor / "index.js").write_text("export function vendored() {}\n", encoding="utf-8")
    (repo / "image.png").write_bytes(b"\x89PNG\0binary")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "local@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Local User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True, text=True
    )
    return repo


def test_indexer_captures_files_symbols_chunks_and_git_metadata(tmp_path: Path) -> None:
    repo = create_test_repo(tmp_path)
    embedder = KeywordEmbedder()
    indexer = RepoIndexer(embedder=embedder, vector_store=InMemoryVectorStore())

    snapshot = indexer.index(repo)
    indexed_paths = {indexed_file.metadata.relative_path for indexed_file in snapshot.files}
    symbols = {symbol.name for indexed_file in snapshot.files for symbol in indexed_file.symbols}
    imports = {item for indexed_file in snapshot.files for item in indexed_file.imports}
    exports = {item for indexed_file in snapshot.files for item in indexed_file.exports}

    assert indexed_paths == {"app.py", "frontend.ts"}
    assert "Widget" in symbols
    assert "render" in symbols
    assert "authenticate_user" in symbols
    assert "makeWidget" in symbols
    assert "os" in imports
    assert "makeWidget" in exports
    assert snapshot.git_commit is not None
    assert snapshot.status.indexed_files == INDEXED_CODE_FILES
    assert snapshot.status.skipped_binary_files == 1
    assert snapshot.status.skipped_ignored_files >= MIN_IGNORED_FILES
    assert snapshot.status.embedded_chunks == snapshot.status.indexed_chunks


def test_exact_symbol_and_semantic_search(tmp_path: Path) -> None:
    repo = create_test_repo(tmp_path)
    indexer = RepoIndexer(embedder=KeywordEmbedder(), vector_store=InMemoryVectorStore())
    indexer.index(repo)

    exact = indexer.search_exact(repo, "authenticate_user")
    symbols = indexer.search_symbols("Widget")
    semantic = indexer.search_semantic("authentication token", limit=1)

    assert exact[0].file_path == "app.py"
    assert exact[0].line_number > 0
    assert {symbol.name for symbol in symbols} >= {"Widget", "makeWidget"}
    assert semantic[0].chunk.symbol_name == "authenticate_user"


def test_incremental_reindex_skips_unchanged_files(tmp_path: Path) -> None:
    repo = create_test_repo(tmp_path)
    embedder = KeywordEmbedder()
    indexer = RepoIndexer(embedder=embedder, vector_store=InMemoryVectorStore())

    first = indexer.index(repo)
    second = indexer.index(repo)
    (repo / "app.py").write_text(
        (repo / "app.py").read_text(encoding="utf-8") + "\nVALUE = 1\n", encoding="utf-8"
    )
    third = indexer.index(repo)

    assert first.status.indexed_files == INDEXED_CODE_FILES
    assert second.status.indexed_files == 0
    assert second.status.skipped_unchanged_files == INDEXED_CODE_FILES
    assert third.status.indexed_files == 1
    assert third.status.skipped_unchanged_files == 1
