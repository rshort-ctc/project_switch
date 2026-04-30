import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.indexing.git import recent_history
from app.indexing.service import RepoIndexer
from app.indexing.types import CodeChunk, CodeSymbol, RepoIndexSnapshot
from app.retrieval.types import (
    ContextBundle,
    ContextCitation,
    RetrievalLane,
    RetrievalQuery,
    RetrievalResult,
)

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./-]{3,}")
DEFAULT_MAX_TERMS = 8
REPO_PATH_AND_QUERY_ARGS = 2


@dataclass(frozen=True)
class _Candidate:
    chunk: CodeChunk
    lane: RetrievalLane
    score: float
    reason: str


@dataclass(frozen=True)
class _MergedCandidate:
    chunk: CodeChunk
    score: float
    reasons: tuple[str, ...]
    lanes: frozenset[RetrievalLane]


class RetrievalEngine:
    def __init__(
        self,
        *,
        indexer: RepoIndexer | None = None,
        snapshot: RepoIndexSnapshot | None = None,
    ) -> None:
        self.indexer = indexer
        self.snapshot = snapshot

    def index(self, repo_path: Path) -> RepoIndexSnapshot:
        if self.indexer is None:
            raise RuntimeError("retrieval engine requires an indexer")
        self.snapshot = self.indexer.index(repo_path)
        return self.snapshot

    def retrieve(
        self,
        *args: object,
        snapshot: RepoIndexSnapshot | None = None,
        indexer: RepoIndexer | None = None,
    ) -> RetrievalResult:
        query = self._resolve_query(args)
        active_snapshot = snapshot or self.snapshot
        if active_snapshot is None:
            raise RuntimeError("repository has not been indexed")
        active_indexer = indexer or self.indexer
        if active_indexer is None:
            raise RuntimeError("retrieval engine requires an indexer")
        retrieval_query = query if isinstance(query, RetrievalQuery) else RetrievalQuery(task=query)
        chunks_by_id = _chunks_by_id(active_snapshot)
        chunks_by_path = _chunks_by_path(active_snapshot)
        terms = _query_terms(retrieval_query.task)

        candidates: list[_Candidate] = []
        candidates.extend(
            self._exact_text_candidates(
                retrieval_query, active_snapshot, active_indexer, chunks_by_path, terms
            )
        )
        candidates.extend(
            self._symbol_candidates(retrieval_query, active_indexer, chunks_by_path, terms)
        )
        candidates.extend(self._semantic_candidates(retrieval_query, active_indexer, chunks_by_id))
        candidates.extend(
            self._file_path_candidates(retrieval_query, active_snapshot, chunks_by_path, terms)
        )
        candidates.extend(
            self._import_dependency_candidates(
                retrieval_query, active_snapshot, chunks_by_path, terms
            )
        )
        if retrieval_query.enable_git_history:
            candidates.extend(
                self._git_history_candidates(
                    retrieval_query, active_snapshot, chunks_by_path, terms
                )
            )

        candidates.extend(self._test_pair_candidates(candidates, active_snapshot, chunks_by_path))
        merged = _deduplicate_overlapping(candidates)
        ranked = sorted(merged, key=lambda item: item.score, reverse=True)

        bundles, omitted = _fit_budget(
            ranked,
            max_bundles=retrieval_query.max_bundles,
            max_context_tokens=retrieval_query.max_context_tokens,
        )
        return RetrievalResult(
            query=retrieval_query,
            bundles=tuple(bundles),
            total_estimated_tokens=sum(bundle.estimated_tokens for bundle in bundles),
            omitted_reasons=tuple(omitted),
        )

    @staticmethod
    def _resolve_query(args: tuple[object, ...]) -> RetrievalQuery | str:
        if len(args) == 1 and isinstance(args[0], RetrievalQuery | str):
            return args[0]
        if len(args) == REPO_PATH_AND_QUERY_ARGS and isinstance(
            args[1],
            RetrievalQuery | str,
        ):
            return args[1]
        raise TypeError("retrieve expects query or repo_path, query")

    def _exact_text_candidates(
        self,
        query: RetrievalQuery,
        snapshot: RepoIndexSnapshot,
        indexer: RepoIndexer,
        chunks_by_path: dict[str, list[CodeChunk]],
        terms: tuple[str, ...],
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        seen: set[tuple[str, int]] = set()
        for term in terms[: query.per_lane_limit]:
            results = indexer.search_exact(snapshot.repo_path, term, limit=query.per_lane_limit)
            for result in results:
                key = (result.file_path, result.line_number)
                if key in seen:
                    continue
                seen.add(key)
                chunk = _chunk_for_line(
                    chunks_by_path.get(result.file_path, []), result.line_number
                )
                if chunk is None:
                    continue
                candidates.append(
                    _Candidate(
                        chunk=chunk,
                        lane=RetrievalLane.EXACT_TEXT,
                        score=90.0,
                        reason=f"exact text match for '{term}' on line {result.line_number}",
                    )
                )
        return candidates

    def _symbol_candidates(
        self,
        query: RetrievalQuery,
        indexer: RepoIndexer,
        chunks_by_path: dict[str, list[CodeChunk]],
        terms: tuple[str, ...],
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        seen: set[tuple[str, str]] = set()
        for term in terms[: query.per_lane_limit]:
            for symbol in indexer.search_symbols(term)[: query.per_lane_limit]:
                key = (symbol.file_path, symbol.name)
                if key in seen:
                    continue
                seen.add(key)
                chunk = _chunk_for_symbol(symbol, chunks_by_path.get(symbol.file_path, []))
                if chunk is None:
                    continue
                candidates.append(
                    _Candidate(
                        chunk=chunk,
                        lane=RetrievalLane.SYMBOL,
                        score=82.0,
                        reason=f"symbol '{symbol.name}' matched '{term}'",
                    )
                )
        return candidates

    def _semantic_candidates(
        self,
        query: RetrievalQuery,
        indexer: RepoIndexer,
        chunks_by_id: dict[str, CodeChunk],
    ) -> list[_Candidate]:
        if not query.enable_semantic:
            return []
        try:
            results = indexer.search_semantic(query.task, limit=query.per_lane_limit)
        except (NotImplementedError, RuntimeError, IndexError):
            return []
        candidates: list[_Candidate] = []
        for result in results:
            chunk = chunks_by_id.get(result.chunk.id)
            if chunk is None:
                continue
            candidates.append(
                _Candidate(
                    chunk=chunk,
                    lane=RetrievalLane.SEMANTIC_VECTOR,
                    score=50.0 + (result.score * 25.0),
                    reason=f"semantic vector similarity {result.score:.3f}",
                )
            )
        return candidates

    def _file_path_candidates(
        self,
        query: RetrievalQuery,
        snapshot: RepoIndexSnapshot,
        chunks_by_path: dict[str, list[CodeChunk]],
        terms: tuple[str, ...],
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        lowered_terms = tuple(term.lower() for term in terms)
        for indexed_file in snapshot.files:
            path = indexed_file.metadata.relative_path
            path_lower = path.lower()
            matched = [term for term in lowered_terms if term in path_lower]
            if not matched:
                continue
            for chunk in _top_file_chunks(chunks_by_path[path], limit=2):
                candidates.append(
                    _Candidate(
                        chunk=chunk,
                        lane=RetrievalLane.FILE_PATH,
                        score=68.0 + len(matched),
                        reason=f"file path matched query term(s): {', '.join(matched)}",
                    )
                )
        return candidates[: query.per_lane_limit]

    def _import_dependency_candidates(
        self,
        query: RetrievalQuery,
        snapshot: RepoIndexSnapshot,
        chunks_by_path: dict[str, list[CodeChunk]],
        terms: tuple[str, ...],
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        lowered_terms = tuple(term.lower().removeprefix("./") for term in terms)
        for indexed_file in snapshot.files:
            haystack = " ".join([*indexed_file.imports, *indexed_file.exports]).lower()
            matched = [term for term in lowered_terms if term and term in haystack]
            if not matched:
                continue
            chunks = chunks_by_path[indexed_file.metadata.relative_path]
            for chunk in _top_file_chunks(chunks, limit=2):
                candidates.append(
                    _Candidate(
                        chunk=chunk,
                        lane=RetrievalLane.IMPORT_DEPENDENCY,
                        score=64.0 + len(matched),
                        reason=f"import/export metadata matched: {', '.join(matched)}",
                    )
                )
        return candidates[: query.per_lane_limit]

    def _git_history_candidates(
        self,
        query: RetrievalQuery,
        snapshot: RepoIndexSnapshot,
        chunks_by_path: dict[str, list[CodeChunk]],
        terms: tuple[str, ...],
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        lowered_terms = tuple(term.lower() for term in terms)
        for entry in recent_history(snapshot.repo_path):
            subject_lower = entry.subject.lower()
            for file_path in entry.file_paths:
                file_lower = file_path.lower()
                if not any(term in subject_lower or term in file_lower for term in lowered_terms):
                    continue
                for chunk in _top_file_chunks(chunks_by_path.get(file_path, []), limit=1):
                    candidates.append(
                        _Candidate(
                            chunk=chunk,
                            lane=RetrievalLane.GIT_HISTORY,
                            score=58.0,
                            reason=(
                                f"recent git commit {entry.commit[:12]} touched this file: "
                                f"{entry.subject}"
                            ),
                        )
                    )
        return candidates[: query.per_lane_limit]

    def _test_pair_candidates(
        self,
        candidates: list[_Candidate],
        snapshot: RepoIndexSnapshot,
        chunks_by_path: dict[str, list[CodeChunk]],
    ) -> list[_Candidate]:
        candidate_paths = {candidate.chunk.file_path for candidate in candidates}
        if not candidate_paths:
            return []
        all_paths = {indexed_file.metadata.relative_path for indexed_file in snapshot.files}
        pairs: set[tuple[str, str]] = set()
        for path in candidate_paths:
            for paired in _paired_test_paths(path, all_paths):
                pairs.add((path, paired))
        return [
            _Candidate(
                chunk=chunk,
                lane=RetrievalLane.TEST_PAIRING,
                score=55.0,
                reason=f"paired test/source file for {source_path}",
            )
            for source_path, paired_path in sorted(pairs)
            for chunk in _top_file_chunks(chunks_by_path.get(paired_path, []), limit=1)
        ]


def _chunks_by_id(snapshot: RepoIndexSnapshot) -> dict[str, CodeChunk]:
    return {chunk.id: chunk for indexed_file in snapshot.files for chunk in indexed_file.chunks}


def _chunks_by_path(snapshot: RepoIndexSnapshot) -> dict[str, list[CodeChunk]]:
    return {
        indexed_file.metadata.relative_path: indexed_file.chunks for indexed_file in snapshot.files
    }


def _query_terms(task: str) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for match in TOKEN_PATTERN.finditer(task):
        term = match.group(0).strip().lower()
        if term not in seen:
            terms.append(term)
            seen.add(term)
        if len(terms) >= DEFAULT_MAX_TERMS:
            break
    return tuple(terms)


def _chunk_for_line(chunks: list[CodeChunk], line_number: int) -> CodeChunk | None:
    containing = [chunk for chunk in chunks if chunk.start_line <= line_number <= chunk.end_line]
    if containing:
        return min(containing, key=_line_span)
    return min(chunks, key=lambda chunk: abs(chunk.start_line - line_number), default=None)


def _chunk_for_symbol(symbol: CodeSymbol, chunks: list[CodeChunk]) -> CodeChunk | None:
    symbol_chunks = [
        chunk
        for chunk in chunks
        if chunk.symbol_name == symbol.name
        and chunk.start_line == symbol.start_line
        and chunk.end_line == symbol.end_line
    ]
    if symbol_chunks:
        return symbol_chunks[0]
    return _chunk_for_line(chunks, symbol.start_line)


def _top_file_chunks(chunks: list[CodeChunk], *, limit: int) -> list[CodeChunk]:
    return sorted(
        chunks,
        key=lambda chunk: (chunk.symbol_name is None, _line_span(chunk), chunk.start_line),
    )[:limit]


def _deduplicate_overlapping(candidates: list[_Candidate]) -> list[_MergedCandidate]:
    merged: list[_MergedCandidate] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        overlap_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if _overlaps(candidate.chunk, existing.chunk)
            ),
            None,
        )
        candidate_merged = _MergedCandidate(
            chunk=candidate.chunk,
            score=candidate.score,
            reasons=(candidate.reason,),
            lanes=frozenset({candidate.lane}),
        )
        if overlap_index is None:
            merged.append(candidate_merged)
            continue
        merged[overlap_index] = _merge_candidate(merged[overlap_index], candidate_merged)
    return merged


def _merge_candidate(left: _MergedCandidate, right: _MergedCandidate) -> _MergedCandidate:
    keep = left
    if right.score > left.score or (
        right.score == left.score and _line_span(right.chunk) < _line_span(left.chunk)
    ):
        keep = right
    return _MergedCandidate(
        chunk=keep.chunk,
        score=max(left.score, right.score),
        reasons=tuple(dict.fromkeys((*left.reasons, *right.reasons))),
        lanes=left.lanes | right.lanes,
    )


def _fit_budget(
    candidates: list[_MergedCandidate],
    *,
    max_bundles: int,
    max_context_tokens: int,
) -> tuple[list[ContextBundle], list[str]]:
    bundles: list[ContextBundle] = []
    omitted: list[str] = []
    used_tokens = 0
    for candidate in candidates:
        if len(bundles) >= max_bundles:
            omitted.append("max bundle count reached")
            break
        estimated_tokens = _estimate_tokens(candidate.chunk.text)
        if used_tokens + estimated_tokens > max_context_tokens:
            omitted.append(
                f"token budget skipped {candidate.chunk.file_path}:"
                f"{candidate.chunk.start_line}-{candidate.chunk.end_line}"
            )
            continue
        used_tokens += estimated_tokens
        primary_lane = sorted(candidate.lanes, key=lambda lane: lane.value)[0]
        bundles.append(
            ContextBundle(
                citation=ContextCitation(
                    file_path=candidate.chunk.file_path,
                    start_line=candidate.chunk.start_line,
                    end_line=candidate.chunk.end_line,
                    lane=primary_lane,
                    chunk_id=candidate.chunk.id,
                    symbol_name=candidate.chunk.symbol_name,
                    git_commit=candidate.chunk.git_commit,
                ),
                text=candidate.chunk.text,
                score=round(candidate.score, 3),
                reasons=candidate.reasons,
                lanes=candidate.lanes,
                estimated_tokens=estimated_tokens,
            )
        )
    return bundles, omitted


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _overlaps(left: CodeChunk, right: CodeChunk) -> bool:
    return (
        left.file_path == right.file_path
        and left.start_line <= right.end_line
        and right.start_line <= left.end_line
    )


def _line_span(chunk: CodeChunk) -> int:
    return chunk.end_line - chunk.start_line + 1


def _paired_test_paths(path: str, all_paths: set[str]) -> set[str]:
    pure_path = PurePosixPath(path)
    stem = pure_path.stem
    suffix = pure_path.suffix
    is_test = stem.startswith("test_") or stem.endswith("_test") or "tests" in pure_path.parts
    candidates: set[str] = set()

    if is_test:
        base_stems = {stem.removeprefix("test_").removesuffix("_test")}
        candidates.update(_source_paths_for_test(all_paths, base_stems))
    else:
        candidates.update(
            {
                f"tests/test_{stem}{suffix}",
                f"test_{stem}{suffix}",
                str(pure_path.with_name(f"test_{stem}{suffix}")),
                str(pure_path.with_name(f"{stem}_test{suffix}")),
            }
        )

    return candidates & all_paths


def _source_paths_for_test(all_paths: set[str], base_stems: set[str]) -> set[str]:
    return {
        candidate
        for candidate in all_paths
        if PurePosixPath(candidate).stem in base_stems
        and "tests" not in PurePosixPath(candidate).parts
    }
