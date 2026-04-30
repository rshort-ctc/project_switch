from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.indexing import InMemoryVectorStore, RepoIndexer
from app.indexing.embeddings import DeterministicEmbedder
from app.model_gateway import LocalModelGateway
from app.model_gateway.errors import ModelGatewayError
from app.model_gateway.schemas import ChatCompletionRequest, ChatMessage, ModelRole
from app.retrieval.engine import RetrievalEngine
from app.retrieval.types import RetrievalQuery
from app.schemas.cli_api import AskContext, ChatRequest, ChatResponse
from app.services.audit import AuditService
from app.services.runs import RunService

router = APIRouter(prefix="/chat", tags=["chat"])

SessionDependency = Annotated[Session, Depends(get_db_session)]

SYSTEM_PROMPT = """You are SWITCH, a fully local coding assistant.
You must preserve local-only operation, cite retrieved files when relevant, avoid claiming
validation ran unless it is present in context, and treat approval/policy boundaries as
mandatory."""


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, session: SessionDependency) -> ChatResponse:
    user_message = _latest_user_message(request)
    contexts: list[AskContext] = []
    context_text = ""
    if request.repository_id is not None and request.max_bundles > 0:
        repository = RunService(session).repositories.get(request.repository_id)
        if repository is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="repository not found",
            )
        repo_path = Path(repository.local_path)
        if not repo_path.exists() or not repo_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="repository path is not a readable directory",
            )
        contexts, context_text = _retrieve_context(repo_path, user_message, request.max_bundles)

    AuditService(session).record(
        event_type="chat.requested",
        summary=f"chat requested model_role={request.model_role} contexts={len(contexts)}",
        subject_type="chat",
        subject_id=request.repository_id,
        actor_user_id=request.actor_user_id,
    )

    try:
        model_role = ModelRole(request.model_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unsupported model role: {request.model_role}",
        ) from exc

    messages = _model_messages(request, context_text)
    try:
        completion = LocalModelGateway().chat_completion(
            ChatCompletionRequest(
                role=model_role,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        )
    except ModelGatewayError:
        answer = _fallback_answer(user_message=user_message, contexts=contexts)
        AuditService(session).record(
            event_type="chat.completed",
            summary="chat completed with retrieval-only fallback",
            subject_type="chat",
            subject_id=request.repository_id,
            actor_user_id=request.actor_user_id,
        )
        session.commit()
        return ChatResponse(
            answer=answer,
            contexts=contexts,
            model=None,
            model_role=request.model_role,
            used_model=False,
            degraded=True,
            stop_reason="model_unavailable",
        )

    AuditService(session).record(
        event_type="chat.completed",
        summary=f"chat completed model={completion.model}",
        subject_type="chat",
        subject_id=request.repository_id,
        actor_user_id=request.actor_user_id,
    )
    session.commit()
    return ChatResponse(
        answer=completion.content,
        contexts=contexts,
        model=completion.model,
        model_role=request.model_role,
        used_model=True,
        degraded=False,
        stop_reason=completion.finish_reason,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        total_tokens=completion.total_tokens,
    )


def _latest_user_message(request: ChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="missing user message",
    )


def _retrieve_context(
    repo_path: Path,
    query: str,
    max_bundles: int,
) -> tuple[list[AskContext], str]:
    indexer = RepoIndexer(embedder=DeterministicEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(repo_path)
    result = RetrievalEngine(indexer=indexer, snapshot=snapshot).retrieve(
        RetrievalQuery(task=query, max_bundles=max_bundles)
    )
    contexts = [
        AskContext(
            path=bundle.citation.file_path,
            start_line=bundle.citation.start_line,
            end_line=bundle.citation.end_line,
            score=bundle.score,
            reasons=list(bundle.reasons),
        )
        for bundle in result.bundles
    ]
    context_lines = []
    for bundle in result.bundles:
        context_lines.append(
            f"{bundle.citation.file_path}:{bundle.citation.start_line}-{bundle.citation.end_line}\n"
            f"{bundle.text}"
        )
    return contexts, "\n\n".join(context_lines)


def _model_messages(request: ChatRequest, context_text: str) -> list[ChatMessage]:
    messages = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
    if context_text:
        messages.append(
            ChatMessage(
                role="system",
                content=f"Retrieved local repository context:\n\n{context_text}",
            )
        )
    messages.extend(
        ChatMessage(role=message.role, content=message.content) for message in request.messages
    )
    return messages


def _fallback_answer(*, user_message: str, contexts: list[AskContext]) -> str:
    if not contexts:
        return (
            "The local model server is unavailable, and no repository context was selected. "
            "Start the local vLLM-compatible model gateway or select a registered repo to "
            "use retrieval."
        )
    citations = "\n".join(
        f"- `{context.path}:{context.start_line}-{context.end_line}` "
        f"score={context.score:.2f}; {', '.join(context.reasons[:3])}"
        for context in contexts
    )
    return (
        "The local model server is unavailable, so I retrieved the most relevant local repository "
        "context instead of generating a model answer.\n\n"
        f"Question: {user_message}\n\n"
        f"Relevant files:\n{citations}"
    )
