from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AgentRunStatus,
    AgentStepStatus,
    ApprovalStatus,
    PatchStatus,
    PolicyDecisionResult,
    RepoIndexStatus,
    TaskStatus,
    ToolCallStatus,
    ValidationStatus,
)


class DurableSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampedSchema(DurableSchema):
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: str = Field(max_length=320)
    display_name: str = Field(max_length=200)


class UserRead(TimestampedSchema):
    id: str
    email: str
    display_name: str
    is_active: bool


class RepositoryCreate(BaseModel):
    name: str = Field(max_length=200)
    local_path: str = Field(max_length=1024)
    default_branch: str = Field(max_length=200)


class RepositoryRead(TimestampedSchema):
    id: str
    name: str
    local_path: str
    default_branch: str
    is_active: bool


class RepoIndexRead(TimestampedSchema):
    id: str
    repository_id: str
    status: RepoIndexStatus
    commit_sha: str
    indexed_at: datetime | None
    exact_index_ready: bool
    symbol_index_ready: bool
    semantic_index_ready: bool
    git_metadata_ready: bool


class TaskCreate(BaseModel):
    repository_id: str
    created_by_user_id: str
    title: str = Field(max_length=300)
    description: str


class TaskRead(TimestampedSchema):
    id: str
    repository_id: str
    created_by_user_id: str
    title: str
    description: str
    status: TaskStatus


class AgentRunCreate(BaseModel):
    task_id: str
    base_branch: str = Field(max_length=200)
    target_branch: str | None = Field(default=None, max_length=200)
    model_name: str | None = Field(default=None, max_length=200)


class AgentRunRead(TimestampedSchema):
    id: str
    task_id: str
    status: AgentRunStatus
    base_branch: str
    target_branch: str | None
    model_name: str | None
    started_at: datetime | None
    completed_at: datetime | None


class AgentStepRead(TimestampedSchema):
    id: str
    agent_run_id: str
    sequence: int
    name: str
    status: AgentStepStatus
    started_at: datetime | None
    completed_at: datetime | None
    summary: str | None


class ToolCallCreate(BaseModel):
    agent_step_id: str
    tool_name: str = Field(max_length=160)
    input_summary: str
    output_summary: str | None = None
    status: ToolCallStatus
    duration_ms: int = Field(ge=0)
    approval_required: bool
    error: str | None = None


class ToolCallRead(TimestampedSchema):
    id: str
    agent_step_id: str
    tool_name: str
    input_summary: str
    output_summary: str | None
    status: ToolCallStatus
    duration_ms: int
    approval_required: bool
    error: str | None


class ApprovalRequestRead(TimestampedSchema):
    id: str
    task_id: str | None
    agent_run_id: str
    requested_by_user_id: str
    decided_by_user_id: str | None
    status: ApprovalStatus
    requested_action: str
    risk_level: str
    reason: str
    diff_summary: str | None
    command: str | None
    decision_note: str | None
    denial_reason: str | None
    decided_at: datetime | None


class ApprovalDecisionRequest(BaseModel):
    decided_by_user_id: str
    decision_note: str | None = None


class ApprovalRequestCreate(BaseModel):
    agent_run_id: str
    requested_by_user_id: str
    requested_action: str = Field(max_length=120)
    risk_level: str = Field(default="medium", max_length=40)
    reason: str
    diff_summary: str | None = None
    command: str | None = Field(default=None, max_length=240)


class PatchArtifactRead(TimestampedSchema):
    id: str
    agent_run_id: str
    approval_request_id: str | None
    status: PatchStatus
    diff_summary: str
    diff_sha256: str
    storage_path: str


class ValidationRunRead(TimestampedSchema):
    id: str
    agent_run_id: str
    patch_artifact_id: str | None
    status: ValidationStatus
    command: str
    exit_code: int | None
    duration_ms: int
    output_summary: str | None


class AuditEventRead(TimestampedSchema):
    id: str
    actor_user_id: str | None
    agent_run_id: str | None
    event_type: str
    summary: str
    subject_type: str
    subject_id: str | None
    trace_id: str | None


class PolicyDecisionRead(TimestampedSchema):
    id: str
    agent_run_id: str | None
    tool_call_id: str | None
    decision: PolicyDecisionResult
    policy_name: str
    reason: str
    enforced: bool
