from dataclasses import dataclass, field
from enum import StrEnum


class RetrievalLane(StrEnum):
    EXACT_TEXT = "exact_text"
    SYMBOL = "symbol"
    SEMANTIC_VECTOR = "semantic_vector"
    FILE_PATH = "file_path"
    IMPORT_DEPENDENCY = "import_dependency"
    GIT_HISTORY = "git_history"
    TEST_PAIRING = "test_pairing"


@dataclass(frozen=True, init=False)
class RetrievalQuery:
    task: str
    max_bundles: int = 8
    max_context_tokens: int = 4000
    per_lane_limit: int = 8
    enable_semantic: bool = True
    enable_git_history: bool = True

    def __init__(
        self,
        task: str | None = None,
        *,
        text: str | None = None,
        max_bundles: int = 8,
        max_context_tokens: int = 4000,
        per_lane_limit: int = 8,
        enable_semantic: bool = True,
        enable_git_history: bool = True,
        max_results: int | None = None,
        max_context_chars: int | None = None,
    ) -> None:
        resolved_task = task if task is not None else text
        if resolved_task is None:
            raise ValueError("retrieval query requires task or text")
        object.__setattr__(self, "task", resolved_task)
        object.__setattr__(self, "max_bundles", max_results or max_bundles)
        object.__setattr__(
            self,
            "max_context_tokens",
            max(1, max_context_chars // 4) if max_context_chars is not None else max_context_tokens,
        )
        object.__setattr__(self, "per_lane_limit", per_lane_limit)
        object.__setattr__(self, "enable_semantic", enable_semantic)
        object.__setattr__(self, "enable_git_history", enable_git_history)


@dataclass(frozen=True)
class ContextCitation:
    file_path: str
    start_line: int
    end_line: int
    lane: RetrievalLane
    chunk_id: str | None = None
    symbol_name: str | None = None
    git_commit: str | None = None


@dataclass(frozen=True)
class ContextBundle:
    citation: ContextCitation
    text: str
    score: float
    reasons: tuple[str, ...]
    lanes: frozenset[RetrievalLane]
    estimated_tokens: int

    @property
    def provenance(self) -> ContextCitation:
        return self.citation

    @property
    def source(self) -> str:
        if len(self.lanes) > 1:
            return "hybrid"
        lane = next(iter(self.lanes))
        if lane is RetrievalLane.EXACT_TEXT:
            return "exact"
        if lane is RetrievalLane.SEMANTIC_VECTOR:
            return "semantic"
        if lane is RetrievalLane.IMPORT_DEPENDENCY:
            return "import"
        return lane.value


@dataclass(frozen=True)
class RetrievalResult:
    query: RetrievalQuery
    bundles: tuple[ContextBundle, ...]
    total_estimated_tokens: int
    omitted_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def contexts(self) -> tuple[ContextBundle, ...]:
        return self.bundles

    @property
    def total_context_chars(self) -> int:
        return sum(len(bundle.text) for bundle in self.bundles)

    @property
    def truncated(self) -> bool:
        return bool(self.omitted_reasons)
