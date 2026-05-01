import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.courthouse import CourthouseService
from app.db.session import get_db_session
from app.model_gateway import LocalModelGateway
from app.model_gateway.errors import ModelGatewayError
from app.model_gateway.schemas import ChatCompletionRequest, ChatMessage, ModelProvider, ModelRole
from app.models.enums import Exposure
from app.sandbox import ChatCodeRunner, ChatCodeRunRequest, ChatCodeRunResponse, SandboxRejected
from app.schemas.cli_api import AskContext, ChatRequest, ChatResponse
from app.services.audit import AuditService
from app.services.repo_qa import (
    RepoQAService,
    RepositoryNotFoundError,
    RepositoryNotIndexedError,
    RepositoryPathError,
    RetrievalUnavailableError,
)

router = APIRouter(prefix="/chat", tags=["chat"])

SessionDependency = Annotated[Session, Depends(get_db_session)]

SYSTEM_PROMPT = """You are SWITCH, an internal operations intelligence assistant.
You must preserve local-only operation, cite retrieved sources when relevant, avoid claiming
validation ran unless it is present in context, draft or propose rather than act, and treat
approval/policy boundaries as mandatory."""


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, session: SessionDependency) -> ChatResponse:
    user_message = _latest_user_message(request)
    try:
        model_role = ModelRole(request.model_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unsupported model role: {request.model_role}",
        ) from exc
    provider = _validate_model_selection(request.provider, request.model)

    AuditService(session).record(
        event_type="chat.requested",
        summary=f"chat requested model_role={request.model_role}",
        subject_type="chat",
        subject_id=request.repository_id,
        actor_user_id=request.actor_user_id,
    )

    if request.repository_id is not None and request.max_bundles == 0:
        try:
            RepoQAService(session).ensure_repository_ready(request.repository_id)
        except RepositoryNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="repository not found",
            ) from exc
        except RepositoryNotIndexedError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except RepositoryPathError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="repository path is not a readable directory",
            ) from exc

    if request.repository_id is not None and request.max_bundles > 0:
        try:
            result = RepoQAService(session).answer_question(
                repository_id=request.repository_id,
                question=user_message,
                max_bundles=request.max_bundles,
                actor_user_id=request.actor_user_id,
                model_role=model_role,
                provider=provider,
                model_override=request.model,
            )
        except RepositoryNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="repository not found",
            ) from exc
        except RepositoryNotIndexedError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except RepositoryPathError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="repository path is not a readable directory",
            ) from exc
        except RetrievalUnavailableError as exc:
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        response = RepoQAService(session).to_ask_response(result)
        AuditService(session).record(
            event_type="chat.completed",
            summary=(
                f"chat completed contexts={len(response.contexts)} "
                f"used_model={response.used_model} degraded={response.degraded}"
            ),
            subject_type="chat",
            subject_id=request.repository_id,
            actor_user_id=request.actor_user_id,
        )
        session.commit()
        return ChatResponse(
            answer=response.answer,
            contexts=response.contexts,
            model=request.model,
            model_role=request.model_role,
            provider=provider.value,
            used_model=response.used_model,
            degraded=response.degraded,
            stop_reason=response.degraded_reason,
        )

    contexts: list[AskContext] = []
    context_text = _compiled_memory_context(session, user_message, request.repository_id)
    messages = _model_messages(request, context_text)
    try:
        completion = LocalModelGateway(provider=provider).chat_completion(
            ChatCompletionRequest(
                role=model_role,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                model_override=request.model,
            )
        )
    except ModelGatewayError:
        answer = _fallback_answer(user_message=user_message)
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
            provider=provider.value,
            used_model=False,
            degraded=True,
            stop_reason="model unavailable",
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
        provider=provider.value,
        used_model=True,
        degraded=False,
        stop_reason=completion.finish_reason,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        total_tokens=completion.total_tokens,
    )


@router.post("/code/run", response_model=ChatCodeRunResponse)
def run_chat_code(request: ChatCodeRunRequest, session: SessionDependency) -> ChatCodeRunResponse:
    AuditService(session).record(
        event_type="chat.code_run.requested",
        summary=f"chat code run requested language={request.language}",
        subject_type="chat_code",
        subject_id=None,
    )
    try:
        response = ChatCodeRunner().run(request)
    except SandboxRejected as exc:
        AuditService(session).record(
            event_type="chat.code_run.denied",
            summary=str(exc),
            subject_type="chat_code",
            subject_id=None,
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    AuditService(session).record(
        event_type="chat.code_run.completed",
        summary=(
            f"chat code run completed exit_code={response.exit_code} timed_out={response.timed_out}"
        ),
        subject_type="chat_code",
        subject_id=None,
    )
    session.commit()
    return response


def _latest_user_message(request: ChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="missing user message",
    )


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


def _compiled_memory_context(
    session: Session, user_message: str, repository_id: str | None
) -> str:
    settings = get_settings()
    if not settings.courthouse_enabled:
        return ""
    try:
        packet = CourthouseService(session).compile_context(
            task=user_message,
            workspace=repository_id,
            exposure_ceiling=Exposure(settings.courthouse_context_default_exposure),
            include_raw_evidence=False,
        )
    except Exception:
        return ""
    return json_dumps_compact(
        {
            "canonical_state": packet.get("canonical_state", []),
            "facts": packet.get("facts", []),
            "open_loops": packet.get("open_loops", []),
            "warnings": packet.get("contradictions_warnings", []),
        }
    )


def json_dumps_compact(payload: object) -> str:
    return json.dumps(payload, default=str, sort_keys=True)


def _fallback_answer(*, user_message: str) -> str:
    return (
        "The local model server is unavailable, and no repository context was selected. "
        "Start the local vLLM-compatible model gateway or select an indexed registered repo "
        f"to use retrieval.\n\nQuestion: {user_message}"
    )


def _validate_model_selection(provider: str, model: str | None) -> ModelProvider:
    try:
        parsed_provider = ModelProvider(provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unsupported model provider: {provider}",
        ) from exc

    uses_ollama_cloud = parsed_provider is ModelProvider.OLLAMA_CLOUD or _is_ollama_cloud_model(
        model
    )
    settings = get_settings()
    if uses_ollama_cloud and (settings.local_only or not settings.allow_ollama_cloud_models):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ollama cloud models are disabled by SWITCH local-only policy.",
        )
    return parsed_provider


def _is_ollama_cloud_model(model: str | None) -> bool:
    return model is not None and (model.endswith(":cloud") or model.endswith("-cloud"))
