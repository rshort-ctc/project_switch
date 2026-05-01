from pydantic import BaseModel, Field

from app.schemas.durable import (
    AgentRunRead,
    AuditEventRead,
    RepositoryRead,
    TaskRead,
    ValidationRunRead,
)


class AgentModelsResponse(BaseModel):
    planner_model: str | None
    coder_model: str | None
    reviewer_model: str | None
    summarizer_model: str | None
    embedding_model: str | None
    reranker_model: str | None


class ModelCatalogResponse(BaseModel):
    providers: list[str]
    models: list[str]
    models_by_provider: dict[str, list[str]]
    allow_ollama_cloud_models: bool
    local_only: bool


class RepoIndexResponse(BaseModel):
    repository_id: str
    index_id: str
    status: str
    commit_sha: str
    indexed_files: int
    indexed_chunks: int
    skipped_ignored_files: int
    skipped_binary_files: int
    skipped_unchanged_files: int


class RepoStatusResponse(BaseModel):
    repository: RepositoryRead
    latest_index: RepoIndexResponse | None = None


class AskRequest(BaseModel):
    repository_id: str
    question: str = Field(min_length=1)
    max_bundles: int = Field(default=5, ge=1, le=20)


class AskContext(BaseModel):
    path: str
    start_line: int
    end_line: int
    score: float
    reasons: list[str]
    lanes: list[str] = Field(default_factory=list)


class RetrievalSummary(BaseModel):
    total_bundles: int
    lanes_used: list[str]
    total_estimated_tokens: int


class AskResponse(BaseModel):
    question: str
    answer: str
    contexts: list[AskContext]
    used_model: bool = False
    degraded: bool = False
    degraded_reason: str | None = None
    index_id: str | None = None
    retrieval_summary: RetrievalSummary | None = None


class ChatMessageInput(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessageInput] = Field(min_length=1)
    repository_id: str | None = None
    actor_user_id: str | None = None
    model_role: str = Field(default="coder_model")
    provider: str = Field(default="local_vllm")
    model: str | None = Field(default=None, min_length=1)
    max_bundles: int = Field(default=6, ge=0, le=20)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1200, ge=1, le=8000)


class ChatResponse(BaseModel):
    answer: str
    contexts: list[AskContext]
    model: str | None = None
    model_role: str
    provider: str = "local_vllm"
    used_model: bool
    degraded: bool
    stop_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class TaskCreateResponse(BaseModel):
    task: TaskRead
    run: AgentRunRead


class TaskStatusResponse(BaseModel):
    task: TaskRead
    run: AgentRunRead | None = None
    current_state: str | None = None
    agent_step_count: int = 0
    tool_call_count: int = 0
    pending_approval_count: int = 0
    latest_failure_message: str | None = None


class TaskRunRequest(BaseModel):
    actor_user_id: str | None = None


class TaskRunResponse(BaseModel):
    task_id: str
    agent_run_id: str
    status: str
    message: str
    status_url: str


class TaskListResponse(BaseModel):
    tasks: list[TaskRead]


class TaskLogsResponse(BaseModel):
    task_id: str
    events: list[AuditEventRead]


class TaskDiffResponse(BaseModel):
    task_id: str
    diff: str
    changed_files: list[str]


class TaskApplyPatchRequest(BaseModel):
    actor_user_id: str = Field(min_length=1)
    approval_request_id: str = Field(min_length=1)
    unified_diff: str = Field(min_length=1)
    branch: str | None = None
    allow_binary: bool = False


class TaskApplyPatchResponse(BaseModel):
    task_id: str
    success: bool
    changed_files: list[str]
    added_files: list[str]
    deleted_files: list[str]
    patch_artifact_id: str | None = None
    rollback_artifact_id: str | None = None
    approval_required: bool
    error_code: str | None = None
    error_message: str | None = None


class ValidationResultsResponse(BaseModel):
    task_id: str
    validations: list[ValidationRunRead]


class RepositoryListResponse(BaseModel):
    repositories: list[RepositoryRead]


class AuditLogResponse(BaseModel):
    events: list[AuditEventRead]
