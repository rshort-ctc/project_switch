from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
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

    repository: Mapped[Repository] = relationship(back_populates="indexes")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

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


class AgentStep(Base, TimestampMixin):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("agent_run_id", "sequence"),)

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


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(36))
    trace_id: Mapped[str | None] = mapped_column(String(64))


class PolicyDecision(Base, TimestampMixin):
    __tablename__ = "policy_decisions"

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
