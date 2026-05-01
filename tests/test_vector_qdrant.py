import json
from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.vector import CODE_CHUNKS_COLLECTION, CodeChunkPayload, QdrantCodeChunkStore
from app.vector.schemas import VectorPoint, VectorSourceKind

SEARCH_SCORE = 0.91
EXPECTED_QDRANT_REQUESTS = 4


def test_qdrant_collection_creation_upsert_and_search_with_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404, json={"status": "not found"})
        if request.method == "PUT" and request.url.path.endswith(CODE_CHUNKS_COLLECTION):
            return httpx.Response(200, json={"result": True})
        if request.method == "PUT" and request.url.path.endswith("/points"):
            body = json.loads(request.content)
            assert body["points"][0]["payload"]["repo_id"] == "repo-1"
            assert body["points"][0]["payload"]["source_kind"] == "code"
            return httpx.Response(200, json={"result": {"operation_id": 1}})
        if request.method == "POST" and request.url.path.endswith("/points/search"):
            body = json.loads(request.content)
            assert body["filter"]["must"] == [
                {"key": "repo_id", "match": {"value": "repo-1"}},
                {"key": "language", "match": {"value": "python"}},
                {"key": "file_path", "match": {"value": "app.py"}},
                {"key": "symbol_name", "match": {"value": "authenticate_user"}},
                {"key": "chunk_type", "match": {"value": "function"}},
            ]
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": "chunk-1",
                            "score": SEARCH_SCORE,
                            "payload": {"repo_id": "repo-1", "file_path": "app.py"},
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.Client(
        base_url="http://qdrant:6333",
        transport=httpx.MockTransport(handler),
    )
    store = QdrantCodeChunkStore(client=client, settings=Settings(_env_file=None))
    payload = CodeChunkPayload(
        repo_id="repo-1",
        repo_name="switch",
        file_path="app.py",
        language="python",
        commit_sha="abc123",
        chunk_hash="hash",
        chunk_type="function",
        symbol_name="authenticate_user",
        start_line=1,
        end_line=5,
        indexed_at=datetime.now(UTC),
        text_preview="def authenticate_user(): ...",
        source_kind=VectorSourceKind.CODE,
    )

    store.upsert_vectors([VectorPoint(id="chunk-1", vector=[0.1, 0.2], payload=payload)])
    results = store.semantic_search(
        [0.1, 0.2],
        limit=5,
        repo_id="repo-1",
        language="python",
        file_path="app.py",
        symbol_name="authenticate_user",
        chunk_type="function",
    )

    assert results[0].id == "chunk-1"
    assert results[0].score == SEARCH_SCORE
    assert len(requests) == EXPECTED_QDRANT_REQUESTS


def test_qdrant_delete_vectors_by_repo_and_file_path() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"result": True})

    client = httpx.Client(
        base_url="http://qdrant:6333",
        transport=httpx.MockTransport(handler),
    )
    store = QdrantCodeChunkStore(client=client, settings=Settings(_env_file=None))

    store.delete_by_repo_id("repo-1")
    store.delete_by_file_path(repo_id="repo-1", file_path="app.py")

    assert bodies[0]["filter"] == {"must": [{"key": "repo_id", "match": {"value": "repo-1"}}]}
    assert bodies[1]["filter"] == {
        "must": [
            {"key": "repo_id", "match": {"value": "repo-1"}},
            {"key": "file_path", "match": {"value": "app.py"}},
        ]
    }
