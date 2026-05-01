from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AgentRunStatus,
    AgentStepStatus,
    ApprovalStatus,
    AuditStatus,
    AuthorityLevel,
    ClaimStatus,
    ClaimType,
    Exposure,
    PatchStatus,
    PolicyDecisionResult,
    PrivacyClass,
    RepoIndexStatus,
    TaskStatus,
    ToolCallStatus,
    ValidationStatus,
    Verdict,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def uuid_str() -> str:
    return str(uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tasks: Mapped[list["Task"]] = relationship(back_populates="created_by")


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    local_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    default_branch: Mapped[str] = mapped_column(String(200), default="main", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    indexes: Mapped[list["RepoIndex"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class RepoIndex(Base, TimestampMixin):
    __tablename__ = "repo_indexes"
    __table_args__ = (
        Index("ix_repo_indexes_repository_status", "repository_id", "status"),
        Index("ix_repo_indexes_repository_commit", "repository_id", "commit_sha"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[RepoIndexStatus] = mapped_column(
        String(40), default=RepoIndexStatus.PENDING, nullable=False
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exact_index_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    symbol_index_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    semantic_index_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    git_metadata_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vector_collection: Mapped[str] = mapped_column(
        String(120), default="switch_code_chunks", nullable=False
    )
    indexed_file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    indexed_chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    repository: Mapped[Repository] = relationship(back_populates="indexes")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_repository_status", "repository_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(String(40), default=TaskStatus.OPEN, nullable=False)

    repository: Mapped[Repository] = relationship(back_populates="tasks")
    created_by: Mapped[User] = relationship(back_populates="tasks")
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_task_status", "task_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        String(40), default=AgentRunStatus.PENDING, nullable=False
    )
    base_branch: Mapped[str] = mapped_column(String(200), nullable=False)
    target_branch: Mapped[str | None] = mapped_column(String(200))
    model_name: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[Task] = relationship(back_populates="agent_runs")
    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["ApprovalRequest"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    patches: Mapped[list["PatchArtifact"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    validation_runs: Mapped[list["ValidationRun"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    model_calls: Mapped[list["ModelCall"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )


class AgentStep(Base, TimestampMixin):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "sequence"),
        Index("ix_agent_steps_run_status", "agent_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[AgentStepStatus] = mapped_column(
        String(40), default=AgentStepStatus.PENDING, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)

    agent_run: Mapped[AgentRun] = relationship(back_populates="steps")
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="agent_step", cascade="all, delete-orphan"
    )


class ToolCall(Base, TimestampMixin):
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_step_status", "agent_step_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_step_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ToolCallStatus] = mapped_column(
        String(40), default=ToolCallStatus.PENDING, nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    agent_step: Mapped[AgentStep] = relationship(back_populates="tool_calls")
    policy_decisions: Mapped[list["PolicyDecision"]] = relationship(
        back_populates="tool_call", cascade="all, delete-orphan"
    )


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_task_status", "task_id", "status"),
        Index("ix_approval_requests_run_status", "agent_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"))
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    status: Mapped[ApprovalStatus] = mapped_column(
        String(40), default=ApprovalStatus.PENDING, nullable=False
    )
    requested_action: Mapped[str] = mapped_column(
        String(120), default="unspecified", nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String(40), default="medium", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    diff_summary: Mapped[str | None] = mapped_column(Text)
    command: Mapped[str | None] = mapped_column(String(240))
    decision_note: Mapped[str | None] = mapped_column(Text)
    denial_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent_run: Mapped[AgentRun] = relationship(back_populates="approvals")


class PatchArtifact(Base, TimestampMixin):
    __tablename__ = "patch_artifacts"
    __table_args__ = (Index("ix_patch_artifacts_run_status", "agent_run_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    approval_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_requests.id")
    )
    status: Mapped[PatchStatus] = mapped_column(
        String(40), default=PatchStatus.PROPOSED, nullable=False
    )
    diff_summary: Mapped[str] = mapped_column(Text, nullable=False)
    diff_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    agent_run: Mapped[AgentRun] = relationship(back_populates="patches")


class ValidationRun(Base, TimestampMixin):
    __tablename__ = "validation_runs"
    __table_args__ = (Index("ix_validation_runs_run_status", "agent_run_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    patch_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("patch_artifacts.id")
    )
    status: Mapped[ValidationStatus] = mapped_column(
        String(40), default=ValidationStatus.PENDING, nullable=False
    )
    command: Mapped[str] = mapped_column(String(240), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_summary: Mapped[str | None] = mapped_column(Text)

    agent_run: Mapped[AgentRun] = relationship(back_populates="validation_runs")


class ModelCall(Base, TimestampMixin):
    __tablename__ = "model_calls"
    __table_args__ = (
        Index("ix_model_calls_run_status", "agent_run_id", "status"),
        Index("ix_model_calls_role_model", "model_role", "model_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    model_role: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    request_summary: Mapped[str] = mapped_column(Text, nullable=False)
    response_summary: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    request_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)

    agent_run: Mapped[AgentRun | None] = relationship(back_populates="model_calls")


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_subject", "subject_type", "subject_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor: Mapped[str | None] = mapped_column(String(200))
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    action_class: Mapped[str | None] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(36))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str | None] = mapped_column(String(40), default=AuditStatus.EXECUTED.value)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)


class PolicyDecision(Base, TimestampMixin):
    __tablename__ = "policy_decisions"
    __table_args__ = (Index("ix_policy_decisions_run_decision", "agent_run_id", "decision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    tool_call_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tool_calls.id", ondelete="CASCADE")
    )
    decision: Mapped[PolicyDecisionResult] = mapped_column(String(40), nullable=False)
    policy_name: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    enforced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tool_call: Mapped[ToolCall | None] = relationship(back_populates="policy_decisions")


class EvidenceItem(Base, TimestampMixin):
    __tablename__ = "evidence_items"
    __table_args__ = (
        Index("ix_evidence_items_workspace", "workspace"),
        Index("ix_evidence_items_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    drawer_id: Mapped[str | None] = mapped_column(String(120))
    source_uri: Mapped[str | None] = mapped_column(String(1024))
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    adapter_name: Mapped[str | None] = mapped_column(String(160))
    adapter_version: Mapped[str | None] = mapped_column(String(80))
    transform_chain: Mapped[dict[str, object] | None] = mapped_column(JSON)
    privacy_class: Mapped[PrivacyClass] = mapped_column(
        String(40), default=PrivacyClass.INTERNAL, nullable=False
    )
    exposure: Mapped[Exposure] = mapped_column(
        String(40), default=Exposure.PRIVATE_INTERNAL, nullable=False
    )
    workspace: Mapped[str | None] = mapped_column(String(200))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)


class Claim(Base, TimestampMixin):
    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_workspace_status", "workspace", "status"),
        Index("ix_claims_subject_scope", "workspace", "subject", "predicate", "scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(String(40), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(300))
    predicate: Mapped[str | None] = mapped_column(String(160))
    object: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(String(300))
    workspace: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_from_evidence_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evidence_items.id")
    )
    extractor: Mapped[str | None] = mapped_column(String(160))
    extractor_version: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    status: Mapped[ClaimStatus] = mapped_column(
        String(40), default=ClaimStatus.CANDIDATE, nullable=False
    )


class VerdictRecord(Base, TimestampMixin):
    __tablename__ = "verdicts"
    __table_args__ = (
        Index("ix_verdicts_claim_id", "claim_id"),
        Index("ix_verdicts_authority", "authority_level"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("claims.id"), nullable=False)
    verdict: Mapped[Verdict] = mapped_column(String(40), nullable=False)
    authority_level: Mapped[AuthorityLevel] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(160), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reason: Mapped[str | None] = mapped_column(Text)
    supersedes_claim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("claims.id"))
    contradicts_claim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("claims.id"))
    appeal_status: Mapped[str] = mapped_column(String(40), default="none", nullable=False)


class CanonicalState(Base, TimestampMixin):
    __tablename__ = "canonical_state"
    __table_args__ = (
        Index("ix_canonical_state_workspace_key", "workspace", "key"),
        UniqueConstraint("workspace", "key", name="uq_canonical_state_workspace_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    key: Mapped[str] = mapped_column(String(300), nullable=False)
    value_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    workspace: Mapped[str | None] = mapped_column(String(200))
    authority_level: Mapped[AuthorityLevel] = mapped_column(String(40), nullable=False)
    source_verdict_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("verdicts.id"), nullable=False
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)


class OpenLoop(Base, TimestampMixin):
    __tablename__ = "open_loops"
    __table_args__ = (Index("ix_open_loops_workspace_status", "workspace", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    workspace: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocking_question: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    source_evidence_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evidence_items.id")
    )
    source_verdict_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("verdicts.id"))
    stale_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContextSnapshot(Base, TimestampMixin):
    __tablename__ = "context_snapshots"
    __table_args__ = (
        Index("ix_context_snapshots_workspace_created", "workspace", "created_at"),
        Index("ix_context_snapshots_hash", "snapshot_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    workspace: Mapped[str | None] = mapped_column(String(200))
    mode: Mapped[str | None] = mapped_column(String(80))
    compiler_version: Mapped[str] = mapped_column(String(80), nullable=False)
    token_budget: Mapped[int | None] = mapped_column(Integer)
    included_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    excluded_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    warnings_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
