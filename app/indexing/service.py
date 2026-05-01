from dataclasses import replace
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.repositories import RepoIndexRepository
from app.indexing.chunking import chunk_file
from app.indexing.crawler import crawl_files
from app.indexing.embeddings import Embedder
from app.indexing.exact_search import ExactSearchResult, RipgrepSearcher
from app.indexing.git import current_commit
from app.indexing.symbols import extract_symbols
from app.indexing.types import CodeSymbol, IndexedFile, IndexStatus, RepoIndexSnapshot
from app.indexing.vector_store import VectorRecord, VectorSearchResult, VectorStore
from app.models.enums import RepoIndexStatus


class RepoIndexer:
    def __init__(
        self,
        *,
        embedder: Embedder,
        vector_store: VectorStore,
        repository_id: str | None = None,
        repository_name: str | None = None,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.repository_id = repository_id
        self.repository_name = repository_name
        self._file_hashes: dict[str, str] = {}
        self._snapshot: RepoIndexSnapshot | None = None

    def index(self, repo_path: Path) -> RepoIndexSnapshot:
        repo_path = repo_path.resolve()
        git_commit = current_commit(repo_path)
        crawl = crawl_files(repo_path, git_commit=git_commit)
        status = IndexStatus(
            skipped_ignored_files=crawl.skipped_ignored_files,
            skipped_binary_files=crawl.skipped_binary_files,
        )
        indexed_files: list[IndexedFile] = []
        all_records: list[VectorRecord] = []
        for metadata in crawl.files:
            if self._file_hashes.get(metadata.relative_path) == metadata.sha256:
                status.skipped_unchanged_files += 1
                previous = self._previous_file(metadata.relative_path)
                if previous is not None:
                    indexed_files.append(previous)
                continue
            text = metadata.path.read_text(encoding="utf-8", errors="ignore")
            extraction = extract_symbols(
                text=text,
                language=metadata.language,
                file_path=metadata.relative_path,
            )
            chunks = [
                replace(chunk, repo_id=self.repository_id, repo_name=self.repository_name)
                for chunk in chunk_file(metadata=metadata, text=text, symbols=extraction.symbols)
            ]
            embeddings = self.embedder.embed([chunk.text for chunk in chunks])
            all_records.extend(
                VectorRecord(chunk=chunk, embedding=embedding)
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            )
            indexed_files.append(
                IndexedFile(
                    metadata=metadata,
                    symbols=extraction.symbols,
                    imports=extraction.imports,
                    exports=extraction.exports,
                    chunks=chunks,
                )
            )
            self._file_hashes[metadata.relative_path] = metadata.sha256
            status.indexed_files += 1
            status.indexed_chunks += len(chunks)
            status.embedded_chunks += len(embeddings)
        self.vector_store.upsert(all_records)
        snapshot = RepoIndexSnapshot(
            repo_path=repo_path, git_commit=git_commit, files=indexed_files, status=status
        )
        self._snapshot = snapshot
        return snapshot

    def search_exact(
        self, repo_path: Path, query: str, *, limit: int = 20
    ) -> list[ExactSearchResult]:
        return RipgrepSearcher(repo_path.resolve()).search(query, limit=limit)

    def search_symbols(self, query: str) -> list[CodeSymbol]:
        snapshot = self._require_snapshot()
        lowered = query.lower()
        results: list[CodeSymbol] = []
        for indexed_file in snapshot.files:
            results.extend(
                symbol for symbol in indexed_file.symbols if lowered in symbol.name.lower()
            )
        return results

    def search_semantic(self, query: str, *, limit: int = 5) -> list[VectorSearchResult]:
        embedding = self.embedder.embed([query])[0]
        return self.vector_store.search(embedding, limit=limit)

    def _previous_file(self, relative_path: str) -> IndexedFile | None:
        if self._snapshot is None:
            return None
        return next(
            (
                indexed_file
                for indexed_file in self._snapshot.files
                if indexed_file.metadata.relative_path == relative_path
            ),
            None,
        )

    def _require_snapshot(self) -> RepoIndexSnapshot:
        if self._snapshot is None:
            raise RuntimeError("repository has not been indexed")
        return self._snapshot


class PersistentRepoIndexer:
    def __init__(
        self,
        *,
        session: Session,
        repository_id: str,
        repository_name: str,
        embedder: Embedder,
        vector_store: VectorStore,
        vector_collection: str = "switch_code_chunks",
    ) -> None:
        self.session = session
        self.repository_id = repository_id
        self.vector_collection = vector_collection
        self.indexer = RepoIndexer(
            embedder=embedder,
            vector_store=vector_store,
            repository_id=repository_id,
            repository_name=repository_name,
        )
        self.repo_indexes = RepoIndexRepository(session)

    def index(self, repo_path: Path) -> RepoIndexSnapshot:
        repo_path = repo_path.resolve()
        repo_index = self.repo_indexes.create(
            repository_id=self.repository_id,
            commit_sha=current_commit(repo_path) or "unknown",
        )
        repo_index.status = RepoIndexStatus.INDEXING
        try:
            snapshot = self.indexer.index(repo_path)
        except Exception as exc:
            self.repo_indexes.mark_failed(repo_index_id=repo_index.id, error_message=str(exc))
            raise
        self.repo_indexes.mark_ready(
            repo_index_id=repo_index.id,
            indexed_file_count=snapshot.status.indexed_files,
            indexed_chunk_count=snapshot.status.indexed_chunks,
            vector_collection=self.vector_collection,
        )
        return snapshot
