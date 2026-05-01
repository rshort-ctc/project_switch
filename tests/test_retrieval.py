import subprocess
from pathlib import Path

from app.indexing import InMemoryVectorStore, RepoIndexer
from app.retrieval import RetrievalEngine, RetrievalLane, RetrievalQuery

FULL_CONTEXT_BUDGET = 500
AUTH_START_LINE = 7
AUTH_END_LINE = 8
TIGHT_CONTEXT_BUDGET = 12


class KeywordEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(text) for text in texts]


def _embed_text(text: str) -> list[float]:
    lowered = text.lower()
    return [
        float("authenticate" in lowered or "authentication" in lowered),
        float("widget" in lowered),
        float("token" in lowered),
        float("unauthorized" in lowered),
        float("profile" in lowered),
        float(len(lowered.split())),
    ]


def _create_retrieval_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text(
        "\n".join(
            [
                "ignored.py",
                "ignored_tests/",
                "*.log",
            ]
        ),
        encoding="utf-8",
    )
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
    src = repo / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "\n".join(
            [
                "def load_profile(session: str) -> dict[str, str]:",
                "    if session == 'valid-session':",
                "        return {'status': 'ok', 'role': 'admin'}",
                "    # BUG: unauthorized token returns a profile instead of an error",
                "    return {'status': 'ok', 'role': 'guest'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text(
        "\n".join(
            [
                "from app import authenticate_user",
                "",
                "def test_authenticate_user_accepts_token() -> None:",
                "    assert authenticate_user('local-token')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tests / "test_auth.py").write_text(
        "\n".join(
            [
                "from src.auth import load_profile",
                "",
                "",
                "def test_load_profile_rejects_unauthorized_token() -> None:",
                "    result = load_profile('invalid-token')",
                "    assert result['status'] == 'unauthorized'",
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
    (repo / "ignored.py").write_text(
        "def ignored_leak() -> str:\n    return 'ignored unauthorized token profile'\n",
        encoding="utf-8",
    )
    ignored_tests = repo / "ignored_tests"
    ignored_tests.mkdir()
    (ignored_tests / "test_leak.py").write_text(
        "def test_ignored_secret_case() -> None:\n    assert 'unauthorized token profile'\n",
        encoding="utf-8",
    )
    (repo / ".env").write_text("SWITCH_TOKEN=local-secret-value\n", encoding="utf-8")
    (repo / "secret_config.py").write_text(
        "API_KEY = 'sk-local-secret-value'\nUNAUTHORIZED_TOKEN_PROFILE = True\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "local@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Local User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial authentication app"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo


def test_retrieval_engine_returns_ranked_hybrid_bundles_with_precise_citations(
    tmp_path: Path,
) -> None:
    repo = _create_retrieval_repo(tmp_path)
    indexer = RepoIndexer(embedder=KeywordEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(repo)

    result = RetrievalEngine().retrieve(
        RetrievalQuery(
            task="Fix authenticate_user in app.py using os import and initial authentication tests",
            max_context_tokens=FULL_CONTEXT_BUDGET,
            per_lane_limit=6,
        ),
        snapshot=snapshot,
        indexer=indexer,
    )

    assert result.bundles
    lanes = {lane for bundle in result.bundles for lane in bundle.lanes}
    assert RetrievalLane.EXACT_TEXT in lanes
    assert RetrievalLane.SYMBOL in lanes
    assert RetrievalLane.SEMANTIC_VECTOR in lanes
    assert RetrievalLane.FILE_PATH in lanes
    assert RetrievalLane.IMPORT_DEPENDENCY in lanes
    assert RetrievalLane.GIT_HISTORY in lanes
    assert RetrievalLane.TEST_PAIRING in lanes
    assert result.total_estimated_tokens <= FULL_CONTEXT_BUDGET

    auth_bundle = next(
        bundle for bundle in result.bundles if bundle.citation.symbol_name == "authenticate_user"
    )
    assert auth_bundle.citation.file_path == "app.py"
    assert auth_bundle.citation.start_line == AUTH_START_LINE
    assert auth_bundle.citation.end_line == AUTH_END_LINE
    assert any("exact text match" in reason for reason in auth_bundle.reasons)
    assert any("symbol" in reason for reason in auth_bundle.reasons)

    paired_test = next(
        bundle for bundle in result.bundles if bundle.citation.file_path == "tests/test_app.py"
    )
    assert RetrievalLane.TEST_PAIRING in paired_test.lanes


def test_bug_like_query_finds_relevant_source_and_test_files(tmp_path: Path) -> None:
    repo = _create_retrieval_repo(tmp_path)
    indexer = RepoIndexer(embedder=KeywordEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(repo)

    result = RetrievalEngine().retrieve(
        RetrievalQuery(
            task="bug: unauthorized login token returns profile",
            max_bundles=8,
            max_context_tokens=FULL_CONTEXT_BUDGET,
            per_lane_limit=8,
        ),
        snapshot=snapshot,
        indexer=indexer,
    )

    paths = {bundle.citation.file_path for bundle in result.bundles}
    assert "src/auth.py" in paths
    assert "tests/test_auth.py" in paths
    assert any("unauthorized token returns a profile" in bundle.text for bundle in result.bundles)
    assert any(
        "test_load_profile_rejects_unauthorized_token" in bundle.text for bundle in result.bundles
    )


def test_retrieval_engine_deduplicates_overlapping_chunks_and_honors_budget(
    tmp_path: Path,
) -> None:
    repo = _create_retrieval_repo(tmp_path)
    indexer = RepoIndexer(embedder=KeywordEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(repo)

    result = RetrievalEngine().retrieve(
        RetrievalQuery(
            task="authenticate_user authenticate token app.py",
            max_bundles=10,
            max_context_tokens=TIGHT_CONTEXT_BUDGET,
            per_lane_limit=8,
        ),
        snapshot=snapshot,
        indexer=indexer,
    )

    ranges = [
        (bundle.citation.file_path, bundle.citation.start_line, bundle.citation.end_line)
        for bundle in result.bundles
    ]
    assert len(ranges) == len(set(ranges))
    assert result.total_estimated_tokens <= TIGHT_CONTEXT_BUDGET
    assert result.omitted_reasons


def test_ignored_and_secret_files_are_not_retrieved(tmp_path: Path) -> None:
    repo = _create_retrieval_repo(tmp_path)
    indexer = RepoIndexer(embedder=KeywordEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(repo)

    result = RetrievalEngine().retrieve(
        RetrievalQuery(
            task="ignored secret unauthorized token profile API_KEY",
            max_bundles=10,
            max_context_tokens=800,
            per_lane_limit=10,
        ),
        snapshot=snapshot,
        indexer=indexer,
    )

    paths = {bundle.citation.file_path for bundle in result.bundles}
    assert "ignored.py" not in paths
    assert "ignored_tests/test_leak.py" not in paths
    assert ".env" not in paths
    assert "secret_config.py" not in paths
    assert all("API_KEY" not in bundle.text for bundle in result.bundles)


def test_generated_next_cache_files_are_not_indexed(tmp_path: Path) -> None:
    repo = _create_retrieval_repo(tmp_path)
    next_cache = repo / "dashboard" / ".next" / "dev" / "server" / "app"
    next_cache.mkdir(parents=True)
    (next_cache / "react-loadable-manifest.json").write_text(
        '{"hello":"generated cache"}',
        encoding="utf-8",
    )
    indexer = RepoIndexer(embedder=KeywordEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(repo)

    indexed_paths = {indexed_file.metadata.relative_path for indexed_file in snapshot.files}

    assert "dashboard/.next/dev/server/app/react-loadable-manifest.json" not in indexed_paths


def test_conversational_stopwords_do_not_drive_exact_retrieval(tmp_path: Path) -> None:
    repo = _create_retrieval_repo(tmp_path)
    indexer = RepoIndexer(embedder=KeywordEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(repo)

    result = RetrievalEngine().retrieve(
        RetrievalQuery(
            task="hello can you check the current repo",
            max_bundles=8,
            max_context_tokens=FULL_CONTEXT_BUDGET,
            per_lane_limit=8,
        ),
        snapshot=snapshot,
        indexer=indexer,
    )

    assert all(
        not any("exact text match for 'hello'" in reason for reason in bundle.reasons)
        for bundle in result.bundles
    )
