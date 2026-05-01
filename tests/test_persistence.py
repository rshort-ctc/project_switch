import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.repositories import ModelCallRepository, RepoIndexRepository
from app.models.entities import AgentRun, AuditEvent, ModelCall, RepoIndex, ToolCall
from app.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    PolicyDecisionResult,
    ToolCallStatus,
)
from app.services import AuditService, RunService, ToolCallService
from app.services.exceptions import InvalidStatusTransitionError

TOOL_DURATION_MS = 123
INDEXED_FILE_COUNT = 2
INDEXED_CHUNK_COUNT = 4


def create_run_graph(session: Session) -> tuple[RunService, str, str, str]:
    service = RunService(session)
    user = service.create_user(email="local@example.test", display_name="Local User")
    repository = service.register_repository(
        name="switch",
        local_path="/repos/switch",
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Add persistence",
        description="Create durable state model",
    )
    run = service.create_agent_run(
        task_id=task.id,
        base_branch="feature/persistence",
        model_name="local-model",
    )
    return service, user.id, task.id, run.id


def test_entity_creation_is_durable(session: Session) -> None:
    _, _, task_id, run_id = create_run_graph(session)
    session.commit()

    task_count = len(
        session.execute(select(AgentRun).where(AgentRun.task_id == task_id)).scalars().all()
    )
    audit_count = len(
        session.execute(select(AuditEvent).where(AuditEvent.agent_run_id == run_id)).scalars().all()
    )

    assert task_count == 1
    assert audit_count == 1


def test_model_calls_are_durable_canonical_metadata(session: Session) -> None:
    _, _, _, run_id = create_run_graph(session)
    repository = ModelCallRepository(session)

    call = repository.create(
        agent_run_id=run_id,
        model_role="coder_model",
        model_name="local-coder",
        endpoint="http://localhost:8001/v1",
        status="succeeded",
        request_summary="summarized prompt only",
        response_summary="summarized response only",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        duration_ms=42,
        request_metadata={"local_only": True},
    )
    session.commit()

    persisted = session.get(ModelCall, call.id)
    assert persisted is not None
    assert persisted.agent_run_id == run_id
    assert persisted.request_metadata == {"local_only": True}


def test_repo_index_status_records_postgres_truth_for_qdrant_rebuild(session: Session) -> None:
    service, _, _, _ = create_run_graph(session)
    repository = service.repositories.list()[0]
    repo_indexes = RepoIndexRepository(session)
    repo_index = repo_indexes.create(repository_id=repository.id, commit_sha="abc123")

    repo_indexes.mark_ready(
        repo_index_id=repo_index.id,
        indexed_file_count=INDEXED_FILE_COUNT,
        indexed_chunk_count=INDEXED_CHUNK_COUNT,
        vector_collection="switch_code_chunks",
    )
    session.commit()

    persisted = session.get(RepoIndex, repo_index.id)
    assert persisted is not None
    assert persisted.status == "ready"
    assert persisted.vector_collection == "switch_code_chunks"
    assert persisted.indexed_file_count == INDEXED_FILE_COUNT
    assert persisted.indexed_chunk_count == INDEXED_CHUNK_COUNT


def test_agent_run_status_transitions_are_validated(session: Session) -> None:
    service, _, _, run_id = create_run_graph(session)

    running = service.transition_run(agent_run_id=run_id, status=AgentRunStatus.RUNNING)
    completed = service.transition_run(agent_run_id=run_id, status=AgentRunStatus.COMPLETED)

    assert running.started_at is not None
    assert completed.completed_at is not None
    with pytest.raises(InvalidStatusTransitionError):
        service.transition_run(agent_run_id=run_id, status=AgentRunStatus.RUNNING)


def test_approval_status_transition_is_recorded(session: Session) -> None:
    service, user_id, _, run_id = create_run_graph(session)
    service.transition_run(agent_run_id=run_id, status=AgentRunStatus.RUNNING)

    approval = service.request_approval(
        agent_run_id=run_id,
        requested_by_user_id=user_id,
        reason="Patch writes require approval",
    )
    decided = service.decide_approval(
        approval_request_id=approval.id,
        decided_by_user_id=user_id,
        status=ApprovalStatus.APPROVED,
        decision_note="Approved for local branch output",
    )

    assert decided.status == ApprovalStatus.APPROVED
    assert decided.decided_at is not None


def test_tool_calls_capture_required_trace_fields_and_redact_secrets(session: Session) -> None:
    run_service, _, _, run_id = create_run_graph(session)
    step = run_service.create_step(agent_run_id=run_id, sequence=1, name="validate")
    service = ToolCallService(session)

    tool_call = service.record_tool_call(
        agent_step_id=step.id,
        agent_run_id=run_id,
        tool_name="pytest",
        input_summary="run tests token=super-secret",
        output_summary="passed",
        status=ToolCallStatus.SUCCEEDED,
        duration_ms=TOOL_DURATION_MS,
        approval_required=False,
    )
    decision = service.record_policy_decision(
        decision=PolicyDecisionResult.ALLOWED,
        policy_name="validation_allowlist",
        reason="command allowed password=hunter2",
        enforced=True,
        agent_run_id=run_id,
        tool_call_id=tool_call.id,
    )

    persisted = session.get(ToolCall, tool_call.id)
    assert persisted is not None
    assert persisted.tool_name == "pytest"
    assert persisted.output_summary == "passed"
    assert persisted.status == ToolCallStatus.SUCCEEDED
    assert persisted.duration_ms == TOOL_DURATION_MS
    assert persisted.approval_required is False
    assert "super-secret" not in persisted.input_summary
    assert "hunter2" not in decision.reason


def test_audit_events_can_be_written_and_queried(session: Session) -> None:
    _, user_id, _, run_id = create_run_graph(session)
    audit = AuditService(session)

    audit.record(
        event_type="custom.event",
        summary="manual audit token=secret-value",
        subject_type="agent_run",
        subject_id=run_id,
        actor_user_id=user_id,
        agent_run_id=run_id,
        trace_id="trace-1",
    )

    events = audit.list_for_run(run_id)
    assert [event.event_type for event in events] == ["agent_run.created", "custom.event"]
    assert "secret-value" not in events[-1].summary
