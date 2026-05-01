from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.repositories import ModelCallRepository, RepoIndexRepository
from app.indexing.embeddings import LocalModelEmbedder
from app.indexing.exact_search import ExactSearchResult, RipgrepSearcher
from app.model_gateway import LocalModelGateway
from app.model_gateway.errors import ModelGatewayError
from app.model_gateway.registry import ModelRegistry
from app.model_gateway.schemas import ChatCompletionRequest, ChatMessage, ModelProvider, ModelRole
from app.models.entities import RepoIndex, Repository
from app.models.enums import RepoIndexStatus
from app.schemas.cli_api import AskContext, AskResponse, RetrievalSummary
from app.services.audit import AuditService
from app.services.runs import RunService
from app.vector import QdrantCodeChunkStore, QdrantStoreError

DEFAULT_CONTEXT_TOKEN_BUDGET = 4000
CONTEXT_WINDOW_LINES = 8
EXACT_SCORE = 90.0
SEMANTIC_SCORE_MULTIPLIER = 100.0
MODEL_MAX_TOKENS = 900
MIN_QUERY_TERM_LENGTH = 3
QUERY_STOPWORDS = {
    "a",
    "about",
    "and",
    "are",
    "can",
    "check",
    "code",
    "current",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "repo",
    "repository",
    "the",
    "this",
    "to",
    "was",
    "what",
    "where",
    "you",
}


class RepoQAError(RuntimeError):
    pass


class RepositoryNotFoundError(RepoQAError):
    pass


class RepositoryPathError(RepoQAError):
    pass


class RepositoryNotIndexedError(RepoQAError):
    pass


class RetrievalUnavailableError(RepoQAError):
    pass


@dataclass(frozen=True)
class QAContextBundle:
    path: str
    start_line: int
    end_line: int
    score: float
    text: str
    reasons: list[str]
    lanes: list[str]
    symbol_name: str | None = None


@dataclass(frozen=True)
class QAResult:
    question: str
    answer: str
    contexts: list[QAContextBundle]
    used_model: bool
    degraded: bool
    degraded_reason: str | None
    index_id: str
    total_estimated_tokens: int


@dataclass
class _MutableContext:
    path: str
    start_line: int
    end_line: int
    score: float
    text: str
    reasons: list[str] = field(default_factory=list)
    lanes: list[str] = field(default_factory=list)
    symbol_name: str | None = None


class RepoQAService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        model_gateway: LocalModelGateway | None = None,
        qdrant_store: QdrantCodeChunkStore | None = None,
        embedder: LocalModelEmbedder | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.audit = AuditService(session)
        self.repo_indexes = RepoIndexRepository(session)
        self.model_calls = ModelCallRepository(session)
        self.model_gateway = model_gateway
        self.qdrant_store = qdrant_store
        self.embedder = embedder

    def answer_question(
        self,
        *,
        repository_id: str,
        question: str,
        max_bundles: int,
        actor_user_id: str | None = None,
        model_role: ModelRole | None = None,
        provider: ModelProvider = ModelProvider.LOCAL_VLLM,
        model_override: str | None = None,
        generate_answer: bool = True,
    ) -> QAResult:
        repository, index = self._ready_repository(repository_id)
        self.audit.record(
            event_type="ask.started",
            summary=f"ask started repo_id={repository.id} max_bundles={max_bundles}",
            subject_type="repository",
            subject_id=repository.id,
            actor_user_id=actor_user_id,
        )
        try:
            contexts = self.retrieve_context(
                repository=repository,
                index=index,
                question=question,
                max_bundles=max_bundles,
            )
        except Exception as exc:
            self.audit.record(
                event_type="ask.failed",
                summary=f"ask failed repo_id={repository.id}: {exc}",
                subject_type="repository",
                subject_id=repository.id,
                actor_user_id=actor_user_id,
            )
            raise

        answer = self._context_only_answer(question=question, contexts=contexts)
        used_model = False
        degraded = False
        degraded_reason: str | None = None

        selected_role = model_role or self._default_answer_role()
        if generate_answer and selected_role is not None:
            model_answer = self._generate_answer(
                question=question,
                contexts=contexts,
                role=selected_role,
                provider=provider,
                model_override=model_override,
                repository_id=repository.id,
            )
            if model_answer is None:
                degraded = True
                degraded_reason = "model unavailable"
                self.audit.record(
                    event_type="ask.degraded",
                    summary="ask returned retrieved context because model generation failed",
                    subject_type="repository",
                    subject_id=repository.id,
                    actor_user_id=actor_user_id,
                )
            else:
                answer = model_answer
                used_model = True
        elif generate_answer:
            degraded = True
            degraded_reason = "model not configured"
            self.audit.record(
                event_type="ask.degraded",
                summary="ask returned retrieved context because no answer model is configured",
                subject_type="repository",
                subject_id=repository.id,
                actor_user_id=actor_user_id,
            )

        self.audit.record(
            event_type="ask.completed",
            summary=(
                f"ask completed repo_id={repository.id} contexts={len(contexts)} "
                f"used_model={used_model} degraded={degraded}"
            ),
            subject_type="repository",
            subject_id=repository.id,
            actor_user_id=actor_user_id,
        )
        return QAResult(
            question=question,
            answer=answer,
            contexts=contexts,
            used_model=used_model,
            degraded=degraded,
            degraded_reason=degraded_reason,
            index_id=index.id,
            total_estimated_tokens=_estimate_tokens(_contexts_for_prompt(contexts)),
        )

    def ensure_repository_ready(self, repository_id: str) -> None:
        self._ready_repository(repository_id)

    def retrieve_context(
        self,
        *,
        repository: Repository,
        index: RepoIndex,
        question: str,
        max_bundles: int,
    ) -> list[QAContextBundle]:
        repo_path = Path(repository.local_path)
        merged: dict[tuple[str, int, int], _MutableContext] = {}
        for match in self._semantic_matches(
            repository=repository,
            index=index,
            question=question,
            limit=max_bundles,
        ):
            _merge_context(merged, match)

        exact_limit = max(max_bundles * 2, max_bundles)
        for match in self._exact_matches(repo_path=repo_path, question=question, limit=exact_limit):
            _merge_context(merged, match)

        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        selected: list[QAContextBundle] = []
        total_tokens = 0
        for context in ranked:
            estimated = _estimate_tokens(context.text)
            if selected and total_tokens + estimated > DEFAULT_CONTEXT_TOKEN_BUDGET:
                continue
            selected.append(
                QAContextBundle(
                    path=context.path,
                    start_line=context.start_line,
                    end_line=context.end_line,
                    score=context.score,
                    text=context.text,
                    reasons=context.reasons,
                    lanes=context.lanes,
                    symbol_name=context.symbol_name,
                )
            )
            total_tokens += estimated
            if len(selected) >= max_bundles:
                break
        return selected

    def to_ask_response(self, result: QAResult) -> AskResponse:
        lanes_used = sorted({lane for context in result.contexts for lane in context.lanes})
        contexts = [
            AskContext(
                path=context.path,
                start_line=context.start_line,
                end_line=context.end_line,
                score=context.score,
                reasons=context.reasons,
                lanes=context.lanes,
            )
            for context in result.contexts
        ]
        return AskResponse(
            question=result.question,
            answer=result.answer,
            contexts=contexts,
            used_model=result.used_model,
            degraded=result.degraded,
            degraded_reason=result.degraded_reason,
            index_id=result.index_id,
            retrieval_summary=RetrievalSummary(
                total_bundles=len(result.contexts),
                lanes_used=lanes_used,
                total_estimated_tokens=result.total_estimated_tokens,
            ),
        )

    def _ready_repository(self, repository_id: str) -> tuple[Repository, RepoIndex]:
        repository = RunService(self.session).repositories.get(repository_id)
        if repository is None:
            raise RepositoryNotFoundError("repository not found")
        repo_path = Path(repository.local_path)
        if not repo_path.exists() or not repo_path.is_dir():
            raise RepositoryPathError("repository path is not a readable directory")
        latest = self.repo_indexes.latest_for_repository(repository_id)
        if (
            latest is None
            or latest.status != RepoIndexStatus.READY
            or not latest.semantic_index_ready
        ):
            raise RepositoryNotIndexedError(
                "Repository is not indexed. Run POST /repos/{repository_id}/index or "
                "`switch repo index <repo-id>` first."
            )
        return repository, latest

    def _semantic_matches(
        self,
        *,
        repository: Repository,
        index: RepoIndex,
        question: str,
        limit: int,
    ) -> list[_MutableContext]:
        try:
            query_vector = self._embedder().embed([question])[0]
            matches = self._qdrant(index).semantic_search(
                query_vector,
                limit=limit,
                repo_id=repository.id,
            )
        except (ModelGatewayError, QdrantStoreError, ValueError, RuntimeError) as exc:
            raise RetrievalUnavailableError(
                f"persistent semantic retrieval unavailable: {exc}"
            ) from exc

        contexts: list[_MutableContext] = []
        for match in matches:
            payload = match.payload
            path = str(payload.get("file_path") or "")
            if not path:
                continue
            start_line = _payload_int(payload.get("start_line"), default=1)
            end_line = _payload_int(payload.get("end_line"), default=start_line)
            text = _read_line_range(Path(repository.local_path), path, start_line, end_line)
            if not text:
                text = str(payload.get("text_preview") or "")
            symbol_name = (
                str(payload["symbol_name"]) if payload.get("symbol_name") is not None else None
            )
            reason = "semantic vector similarity"
            if symbol_name:
                reason = f"{reason} for symbol '{symbol_name}'"
            contexts.append(
                _MutableContext(
                    path=path,
                    start_line=start_line,
                    end_line=end_line,
                    score=match.score * SEMANTIC_SCORE_MULTIPLIER,
                    text=text,
                    reasons=[reason],
                    lanes=["semantic"],
                    symbol_name=symbol_name,
                )
            )
        return contexts

    def _exact_matches(
        self, *, repo_path: Path, question: str, limit: int
    ) -> list[_MutableContext]:
        matches: list[ExactSearchResult] = []
        for term in _query_terms(question):
            try:
                matches.extend(RipgrepSearcher(repo_path).search(term, limit=limit))
            except RuntimeError:
                continue
            if len(matches) >= limit:
                break

        contexts: list[_MutableContext] = []
        seen: set[tuple[str, int]] = set()
        for match in matches[:limit]:
            key = (match.file_path, match.line_number)
            if key in seen:
                continue
            seen.add(key)
            start_line = max(1, match.line_number - CONTEXT_WINDOW_LINES)
            end_line = match.line_number + CONTEXT_WINDOW_LINES
            contexts.append(
                _MutableContext(
                    path=match.file_path,
                    start_line=start_line,
                    end_line=end_line,
                    score=EXACT_SCORE,
                    text=_read_line_range(repo_path, match.file_path, start_line, end_line),
                    reasons=[f"exact text match near line {match.line_number}"],
                    lanes=["exact"],
                )
            )
        return contexts

    def _generate_answer(
        self,
        *,
        question: str,
        contexts: list[QAContextBundle],
        role: ModelRole,
        provider: ModelProvider,
        model_override: str | None,
        repository_id: str,
    ) -> str | None:
        gateway = self.model_gateway or LocalModelGateway(settings=self.settings, provider=provider)
        registry = ModelRegistry(self.settings)
        model_name = model_override or "unconfigured"
        started = time.monotonic()
        request_summary = f"ask answer role={role.value} contexts={len(contexts)}"
        try:
            model_name = model_override or registry.model_for(role)
            completion = gateway.chat_completion(
                ChatCompletionRequest(
                    role=role,
                    messages=_answer_messages(question=question, contexts=contexts),
                    max_tokens=MODEL_MAX_TOKENS,
                    model_override=model_override,
                )
            )
        except ModelGatewayError as exc:
            self.model_calls.create(
                model_role=role.value,
                model_name=model_name,
                endpoint=_provider_endpoint(self.settings, provider),
                status="failed",
                request_summary=request_summary,
                response_summary=None,
                duration_ms=_duration_ms(started),
                error=str(exc),
                request_metadata={
                    "repository_id": repository_id,
                    "degraded": True,
                    "context_count": len(contexts),
                },
            )
            return None

        self.model_calls.create(
            model_role=role.value,
            model_name=completion.model or model_name,
            endpoint=_provider_endpoint(self.settings, provider),
            status="succeeded",
            request_summary=request_summary,
            response_summary=f"answer chars={len(completion.content)}",
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            total_tokens=completion.total_tokens,
            duration_ms=_duration_ms(started),
            request_metadata={
                "repository_id": repository_id,
                "degraded": False,
                "context_count": len(contexts),
            },
        )
        return completion.content

    def _default_answer_role(self) -> ModelRole | None:
        configured = ModelRegistry(self.settings).configured_models()
        for role in (ModelRole.SUMMARIZER, ModelRole.PLANNER, ModelRole.CODER):
            if role in configured:
                return role
        return None

    def _embedder(self) -> LocalModelEmbedder:
        if self.embedder is None:
            self.embedder = LocalModelEmbedder(LocalModelGateway(settings=self.settings))
        return self.embedder

    def _qdrant(self, index: RepoIndex) -> QdrantCodeChunkStore:
        if self.qdrant_store is None:
            self.qdrant_store = QdrantCodeChunkStore(
                endpoint=str(self.settings.vector_store_url),
                collection=index.vector_collection,
                settings=self.settings,
            )
        return self.qdrant_store

    @staticmethod
    def _context_only_answer(*, question: str, contexts: list[QAContextBundle]) -> str:
        if not contexts:
            return (
                "No relevant indexed repository context was found. Rebuild the repository index "
                "or ask a more specific question."
            )
        citations = "\n".join(
            f"- `{context.path}:{context.start_line}-{context.end_line}` "
            f"score={context.score:.2f}; {', '.join(context.reasons[:2])}"
            for context in contexts
        )
        return (
            "I retrieved indexed local repository context, but no model answer was generated.\n\n"
            f"Question: {question}\n\nRelevant files:\n{citations}"
        )


def _answer_messages(*, question: str, contexts: list[QAContextBundle]) -> list[ChatMessage]:
    return [
        ChatMessage(
            role="system",
            content=(
                "You are SWITCH, an internal operations intelligence assistant. Answer only "
                "from the retrieved repository context. Cite file paths and line ranges. "
                "If the context is insufficient, say so directly. Do not invent files, "
                "tests, behavior, or validation results."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Question:\n{question}\n\n"
                f"Retrieved context:\n{_contexts_for_prompt(contexts)}"
            ),
        ),
    ]


def _contexts_for_prompt(contexts: list[QAContextBundle]) -> str:
    return "\n\n".join(
        f"{context.path}:{context.start_line}-{context.end_line}\n{context.text}"
        for context in contexts
    )


def _merge_context(
    contexts: dict[tuple[str, int, int], _MutableContext],
    new_context: _MutableContext,
) -> None:
    key = (new_context.path, new_context.start_line, new_context.end_line)
    existing = contexts.get(key)
    if existing is None:
        contexts[key] = new_context
        return
    existing.score = max(existing.score, new_context.score)
    for reason in new_context.reasons:
        if reason not in existing.reasons:
            existing.reasons.append(reason)
    for lane in new_context.lanes:
        if lane not in existing.lanes:
            existing.lanes.append(lane)


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for raw in query.replace("_", " ").replace("-", " ").split():
        term = "".join(character for character in raw.lower() if character.isalnum())
        if len(term) < MIN_QUERY_TERM_LENGTH or term in QUERY_STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    return terms[:8]


def _read_line_range(repo_path: Path, file_path: str, start_line: int, end_line: int) -> str:
    resolved_repo = repo_path.resolve()
    resolved_file = (resolved_repo / file_path).resolve()
    try:
        resolved_file.relative_to(resolved_repo)
    except ValueError:
        return ""
    if not resolved_file.exists() or not resolved_file.is_file():
        return ""
    lines = resolved_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    start_index = max(start_line - 1, 0)
    end_index = min(end_line, len(lines))
    return "\n".join(lines[start_index:end_index])


def _payload_int(value: object, *, default: int) -> int:
    if isinstance(value, int | str | bytes | bytearray):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _duration_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _provider_endpoint(settings: Settings, provider: ModelProvider) -> str:
    if provider in {ModelProvider.OLLAMA_LOCAL, ModelProvider.OLLAMA_CLOUD}:
        return str(settings.ollama_endpoint)
    return str(settings.vllm_endpoint)
