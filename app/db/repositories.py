from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentRun,
    AgentStep,
    ApprovalRequest,
    AuditEvent,
    ModelCall,
    PatchArtifact,
    PolicyDecision,
    RepoIndex,
    Repository,
    Site,
    Task,
    ToolCall,
    User,
    ValidationRun,
)
from app.models.enums import ApprovalStatus, RepoIndexStatus, SiteStatus, ValidationStatus


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: object) -> None:
        self.session.add(entity)


class UserRepository(BaseRepository):
    def create(self, *, email: str, display_name: str) -> User:
        user = User(email=email, display_name=display_name)
        self.add(user)
        self.session.flush()
        return user

    def get(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)


class SiteRepository(BaseRepository):
    def create(
        self,
        *,
        site_name: str,
        facility_type: str = "unknown",
        address_line_1: str | None = None,
        address_line_2: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        county: str | None = None,
        timezone: str | None = None,
        status: SiteStatus = SiteStatus.UNKNOWN,
        primary_contact_name: str | None = None,
        primary_contact_email: str | None = None,
        primary_contact_phone: str | None = None,
        notes: str | None = None,
    ) -> Site:
        site = Site(
            site_name=site_name,
            facility_type=facility_type,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            state=state,
            zip_code=zip_code,
            county=county,
            timezone=timezone,
            status=status,
            primary_contact_name=primary_contact_name,
            primary_contact_email=primary_contact_email,
            primary_contact_phone=primary_contact_phone,
            notes=notes,
        )
        self.add(site)
        self.session.flush()
        return site

    def get(self, site_id: str) -> Site | None:
        return self.session.get(Site, site_id)

    def list(self, *, status: SiteStatus | None = None) -> Sequence[Site]:
        statement: Select[tuple[Site]] = select(Site)
        if status is not None:
            statement = statement.where(Site.status == status.value)
        statement = statement.order_by(Site.site_name, Site.id)
        return self.session.execute(statement).scalars().all()


class RepositoryRepository(BaseRepository):
    def create(self, *, name: str, local_path: str, default_branch: str) -> Repository:
        repository = Repository(name=name, local_path=local_path, default_branch=default_branch)
        self.add(repository)
        self.session.flush()
        return repository

    def get(self, repository_id: str) -> Repository | None:
        return self.session.get(Repository, repository_id)

    def get_by_local_path(self, local_path: str) -> Repository | None:
        statement: Select[tuple[Repository]] = select(Repository).where(
            Repository.local_path == local_path
        )
        return self.session.execute(statement).scalars().first()

    def list(self) -> Sequence[Repository]:
        statement: Select[tuple[Repository]] = select(Repository).order_by(
            Repository.created_at, Repository.id
        )
        return self.session.execute(statement).scalars().all()


class RepoIndexRepository(BaseRepository):
    def create(self, *, repository_id: str, commit_sha: str) -> RepoIndex:
        index = RepoIndex(repository_id=repository_id, commit_sha=commit_sha)
        self.add(index)
        self.session.flush()
        return index

    def latest_for_repository(self, repository_id: str) -> RepoIndex | None:
        statement: Select[tuple[RepoIndex]] = (
            select(RepoIndex)
            .where(RepoIndex.repository_id == repository_id)
            .order_by(RepoIndex.created_at.desc(), RepoIndex.id.desc())
        )
        return self.session.execute(statement).scalars().first()

    def mark_ready(
        self,
        *,
        repo_index_id: str,
        indexed_file_count: int,
        indexed_chunk_count: int,
        vector_collection: str,
    ) -> RepoIndex:
        index = self.session.get(RepoIndex, repo_index_id)
        if index is None:
            raise ValueError(f"repo index not found: {repo_index_id}")
        index.status = RepoIndexStatus.READY
        index.indexed_at = datetime.now(UTC)
        index.indexed_file_count = indexed_file_count
        index.indexed_chunk_count = indexed_chunk_count
        index.vector_collection = vector_collection
        index.exact_index_ready = True
        index.symbol_index_ready = True
        index.semantic_index_ready = True
        index.git_metadata_ready = True
        return index

    def mark_failed(self, *, repo_index_id: str, error_message: str) -> RepoIndex:
        index = self.session.get(RepoIndex, repo_index_id)
        if index is None:
            raise ValueError(f"repo index not found: {repo_index_id}")
        index.status = RepoIndexStatus.FAILED
        index.error_message = error_message
        return index


class TaskRepository(BaseRepository):
    def create(
        self,
        *,
        repository_id: str,
        created_by_user_id: str,
        title: str,
        description: str,
    ) -> Task:
        task = Task(
            repository_id=repository_id,
            created_by_user_id=created_by_user_id,
            title=title,
            description=description,
        )
        self.add(task)
        self.session.flush()
        return task

    def get(self, task_id: str) -> Task | None:
        return self.session.get(Task, task_id)

    def list(self) -> Sequence[Task]:
        statement: Select[tuple[Task]] = select(Task).order_by(Task.created_at, Task.id)
        return self.session.execute(statement).scalars().all()


class AgentRunRepository(BaseRepository):
    def create(
        self,
        *,
        task_id: str,
        base_branch: str,
        target_branch: str | None = None,
        model_name: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            task_id=task_id,
            base_branch=base_branch,
            target_branch=target_branch,
            model_name=model_name,
        )
        self.add(run)
        self.session.flush()
        return run

    def get(self, agent_run_id: str) -> AgentRun | None:
        return self.session.get(AgentRun, agent_run_id)

    def latest_for_task(self, task_id: str) -> AgentRun | None:
        statement: Select[tuple[AgentRun]] = (
            select(AgentRun)
            .where(AgentRun.task_id == task_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        )
        return self.session.execute(statement).scalars().first()


class AgentStepRepository(BaseRepository):
    def create(self, *, agent_run_id: str, sequence: int, name: str) -> AgentStep:
        step = AgentStep(agent_run_id=agent_run_id, sequence=sequence, name=name)
        self.add(step)
        self.session.flush()
        return step


class ToolCallRepository(BaseRepository):
    def create(
        self,
        *,
        agent_step_id: str,
        tool_name: str,
        input_summary: str,
        output_summary: str | None,
        status: str,
        duration_ms: int,
        approval_required: bool,
        error: str | None,
    ) -> ToolCall:
        tool_call = ToolCall(
            agent_step_id=agent_step_id,
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            duration_ms=duration_ms,
            approval_required=approval_required,
            error=error,
        )
        self.add(tool_call)
        self.session.flush()
        return tool_call


class ApprovalRequestRepository(BaseRepository):
    def create(
        self,
        *,
        agent_run_id: str | None,
        requested_by_user_id: str | None,
        reason: str,
        task_id: str | None = None,
        requested_action: str = "unspecified",
        risk_level: str = "medium",
        diff_summary: str | None = None,
        command: str | None = None,
        requested_by: str | None = None,
        action: str | None = None,
        action_class: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        proposed_payload: dict[str, object] | None = None,
        risk_summary: str | None = None,
        audit_event_id: str | None = None,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            task_id=task_id,
            agent_run_id=agent_run_id,
            requested_by_user_id=requested_by_user_id,
            reason=reason,
            requested_action=requested_action,
            risk_level=risk_level,
            diff_summary=diff_summary,
            command=command,
            requested_by=requested_by or requested_by_user_id,
            action=action or requested_action,
            action_class=action_class,
            target_type=target_type or ("agent_run" if agent_run_id else None),
            target_id=target_id or agent_run_id,
            proposed_payload=proposed_payload or {},
            risk_summary=risk_summary or reason,
            audit_event_id=audit_event_id,
        )
        self.add(approval)
        self.session.flush()
        return approval

    def get(self, approval_request_id: str) -> ApprovalRequest | None:
        return self.session.get(ApprovalRequest, approval_request_id)

    def list_pending(self) -> Sequence[ApprovalRequest]:
        statement: Select[tuple[ApprovalRequest]] = (
            select(ApprovalRequest)
            .where(ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.created_at, ApprovalRequest.id)
        )
        return self.session.execute(statement).scalars().all()

    def list(self) -> Sequence[ApprovalRequest]:
        statement: Select[tuple[ApprovalRequest]] = select(ApprovalRequest).order_by(
            ApprovalRequest.created_at,
            ApprovalRequest.id,
        )
        return self.session.execute(statement).scalars().all()

    def list_by_status(self, status: ApprovalStatus) -> Sequence[ApprovalRequest]:
        statement: Select[tuple[ApprovalRequest]] = (
            select(ApprovalRequest)
            .where(ApprovalRequest.status == status.value)
            .order_by(ApprovalRequest.created_at, ApprovalRequest.id)
        )
        return self.session.execute(statement).scalars().all()

    def list_for_target(self, target_type: str, target_id: str) -> Sequence[ApprovalRequest]:
        statement: Select[tuple[ApprovalRequest]] = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.target_type == target_type,
                ApprovalRequest.target_id == target_id,
            )
            .order_by(ApprovalRequest.created_at, ApprovalRequest.id)
        )
        return self.session.execute(statement).scalars().all()


class PatchArtifactRepository(BaseRepository):
    def create(
        self,
        *,
        agent_run_id: str,
        diff_summary: str,
        diff_sha256: str,
        storage_path: str,
        approval_request_id: str | None = None,
    ) -> PatchArtifact:
        patch = PatchArtifact(
            agent_run_id=agent_run_id,
            approval_request_id=approval_request_id,
            diff_summary=diff_summary,
            diff_sha256=diff_sha256,
            storage_path=storage_path,
        )
        self.add(patch)
        self.session.flush()
        return patch


class ValidationRunRepository(BaseRepository):
    def create(
        self,
        *,
        agent_run_id: str,
        command: str,
        duration_ms: int,
        patch_artifact_id: str | None = None,
        status: ValidationStatus = ValidationStatus.PENDING,
        exit_code: int | None = None,
        output_summary: str | None = None,
    ) -> ValidationRun:
        validation = ValidationRun(
            agent_run_id=agent_run_id,
            patch_artifact_id=patch_artifact_id,
            command=command,
            status=status,
            exit_code=exit_code,
            duration_ms=duration_ms,
            output_summary=output_summary,
        )
        self.add(validation)
        self.session.flush()
        return validation

    def list_for_agent_run(self, agent_run_id: str) -> Sequence[ValidationRun]:
        statement: Select[tuple[ValidationRun]] = (
            select(ValidationRun)
            .where(ValidationRun.agent_run_id == agent_run_id)
            .order_by(ValidationRun.created_at, ValidationRun.id)
        )
        return self.session.execute(statement).scalars().all()


class AuditEventRepository(BaseRepository):
    def create(
        self,
        *,
        event_type: str,
        summary: str,
        subject_type: str,
        subject_id: str | None,
        actor: str | None = None,
        action_class: str | None = None,
        metadata_json: dict[str, object] | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        actor_user_id: str | None = None,
        agent_run_id: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            actor=actor,
            actor_user_id=actor_user_id,
            agent_run_id=agent_run_id,
            event_type=event_type,
            action_class=action_class,
            summary=summary,
            subject_type=subject_type,
            subject_id=subject_id,
            metadata_json=metadata_json or {},
            status=status,
            trace_id=trace_id,
            correlation_id=correlation_id,
        )
        self.add(event)
        self.session.flush()
        return event

    def list_for_run(self, agent_run_id: str) -> Sequence[AuditEvent]:
        statement: Select[tuple[AuditEvent]] = (
            select(AuditEvent)
            .where(AuditEvent.agent_run_id == agent_run_id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return self.session.execute(statement).scalars().all()

    def list_recent(self, *, limit: int = 100) -> Sequence[AuditEvent]:
        statement: Select[tuple[AuditEvent]] = (
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        )
        return self.session.execute(statement).scalars().all()

    def list_by_correlation_id(self, correlation_id: str) -> Sequence[AuditEvent]:
        statement: Select[tuple[AuditEvent]] = (
            select(AuditEvent)
            .where(AuditEvent.correlation_id == correlation_id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return self.session.execute(statement).scalars().all()

    def list_for_target(self, target_type: str, target_id: str | None) -> Sequence[AuditEvent]:
        statement: Select[tuple[AuditEvent]] = (
            select(AuditEvent)
            .where(AuditEvent.subject_type == target_type, AuditEvent.subject_id == target_id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return self.session.execute(statement).scalars().all()


class PolicyDecisionRepository(BaseRepository):
    def create(
        self,
        *,
        decision: str,
        policy_name: str,
        reason: str,
        enforced: bool,
        agent_run_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> PolicyDecision:
        policy_decision = PolicyDecision(
            agent_run_id=agent_run_id,
            tool_call_id=tool_call_id,
            decision=decision,
            policy_name=policy_name,
            reason=reason,
            enforced=enforced,
        )
        self.add(policy_decision)
        self.session.flush()
        return policy_decision


class ModelCallRepository(BaseRepository):
    def create(
        self,
        *,
        model_role: str,
        model_name: str,
        endpoint: str,
        status: str,
        request_summary: str,
        response_summary: str | None = None,
        agent_run_id: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        duration_ms: int = 0,
        error: str | None = None,
        request_metadata: dict[str, object] | None = None,
    ) -> ModelCall:
        call = ModelCall(
            agent_run_id=agent_run_id,
            model_role=model_role,
            model_name=model_name,
            endpoint=endpoint,
            status=status,
            request_summary=request_summary,
            response_summary=response_summary,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            error=error,
            request_metadata=request_metadata or {},
        )
        self.add(call)
        self.session.flush()
        return call
