from collections.abc import Mapping

import httpx

from app.core.config import Settings, get_settings
from app.vector.collections import CODE_CHUNKS_COLLECTION, code_chunks_collection_config
from app.vector.schemas import VectorPoint, VectorSearchMatch


class QdrantStoreError(RuntimeError):
    pass


class QdrantCodeChunkStore:
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        collection: str = CODE_CHUNKS_COLLECTION,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.endpoint = (endpoint or str(self.settings.vector_store_url)).rstrip("/")
        if self.settings.local_only and not self.settings.endpoint_is_local(self.endpoint):
            raise ValueError("Qdrant endpoint must be local when LOCAL_ONLY=true")
        self.collection = collection
        self.client = client or httpx.Client(base_url=self.endpoint, timeout=30)

    def collection_exists(self) -> bool:
        try:
            response = self.client.get(f"/collections/{self.collection}")
            if response.status_code == httpx.codes.NOT_FOUND:
                return False
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            raise QdrantStoreError(f"Qdrant collection check failed: {exc}") from exc

    def create_collection(self, *, vector_size: int) -> None:
        try:
            response = self.client.put(
                f"/collections/{self.collection}",
                json=code_chunks_collection_config(vector_size),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QdrantStoreError(f"Qdrant collection creation failed: {exc}") from exc

    def ensure_collection(self, *, vector_size: int) -> None:
        if not self.collection_exists():
            self.create_collection(vector_size=vector_size)

    def upsert_vectors(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        self.ensure_collection(vector_size=len(points[0].vector))
        try:
            response = self.client.put(
                f"/collections/{self.collection}/points",
                params={"wait": "true"},
                json={
                    "points": [
                        {
                            "id": point.id,
                            "vector": point.vector,
                            "payload": point.payload.to_qdrant_payload(),
                        }
                        for point in points
                    ]
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QdrantStoreError(f"Qdrant vector upsert failed: {exc}") from exc

    def delete_by_repo_id(self, repo_id: str) -> None:
        self._delete_by_filter({"key": "repo_id", "match": {"value": repo_id}})

    def delete_by_file_path(self, *, repo_id: str, file_path: str) -> None:
        self._delete_by_filter(
            {
                "must": [
                    {"key": "repo_id", "match": {"value": repo_id}},
                    {"key": "file_path", "match": {"value": file_path}},
                ]
            }
        )

    def delete_by_commit_sha(self, *, repo_id: str, commit_sha: str) -> None:
        self._delete_by_filter(
            {
                "must": [
                    {"key": "repo_id", "match": {"value": repo_id}},
                    {"key": "commit_sha", "match": {"value": commit_sha}},
                ]
            }
        )

    def semantic_search(
        self,
        query_vector: list[float],
        *,
        limit: int,
        repo_id: str | None = None,
        language: str | None = None,
        file_path: str | None = None,
        symbol_name: str | None = None,
        chunk_type: str | None = None,
    ) -> list[VectorSearchMatch]:
        filters = _payload_filters(
            repo_id=repo_id,
            language=language,
            file_path=file_path,
            symbol_name=symbol_name,
            chunk_type=chunk_type,
        )
        body: dict[str, object] = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
        }
        if filters:
            body["filter"] = {"must": filters}
        try:
            response = self.client.post(f"/collections/{self.collection}/points/search", json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise QdrantStoreError(f"Qdrant semantic search failed: {exc}") from exc
        return [
            VectorSearchMatch(
                id=str(item["id"]),
                score=float(item["score"]),
                payload=dict(item.get("payload") or {}),
            )
            for item in data.get("result", [])
        ]

    def _delete_by_filter(self, selector: Mapping[str, object]) -> None:
        if "key" in selector:
            filter_body: dict[str, object] = {"must": [dict(selector)]}
        else:
            filter_body = dict(selector)
        try:
            response = self.client.post(
                f"/collections/{self.collection}/points/delete",
                params={"wait": "true"},
                json={"filter": filter_body},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QdrantStoreError(f"Qdrant vector delete failed: {exc}") from exc


def _payload_filters(**values: str | None) -> list[dict[str, object]]:
    return [
        {"key": key, "match": {"value": value}}
        for key, value in values.items()
        if value is not None
    ]
