import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    DeterministicCodingAgentWorkflow,
    WorkflowConfig,
    WorkflowInput,
    WorkflowState,
    WorkflowStatus,
    WorkflowStopReason,
)
from app.indexing import InMemoryVectorStore, RepoIndexer
from app.models.entities import AgentStep, AuditEvent, ToolCall
from app.models.enums import AgentRunStatus
from app.retrieval import RetrievalEngine
from app.sandbox import SandboxResult, SandboxRunSpec
from app.sandbox.types import SandboxCommandCategory
from app.security import PermissionLevel, PolicyConfig, PolicyEngine
from app.services.runs import RunService

EXPECTED_RETRY_ATTEMPTS = 2
MIN_MODEL_AUDITS = 4


class WorkflowEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float("add" in text.lower()),
                float("calculator" in text.lower()),
                float("test" in text.lower()),
            ]
            for text in texts
        ]


class ScriptedWorkflowModel:
    def __init__(self, patches: list[dict[str, str]]) -> None:
        self.patches = patches
        self.patch_index = 0
        self.calls: list[WorkflowState] = []

    def complete(
        self,
        *,
        state: WorkflowState,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        self.calls.append(state)
        if state is WorkflowState.CLASSIFY_TASK:
            return {"task_type": "bugfix", "summary": "calculator add failure"}
        if state is WorkflowState.DRAFT_PLAN:
            return {"plan": ["inspect cited calculator code", "patch add implementation"]}
        if state is WorkflowState.RISK_ASSESSMENT:
            return {"risk": "low", "approval_required": False}
        if state in {WorkflowState.GENERATE_PATCH, WorkflowState.REVISE_PATCH_LIMITED}:
            patch = self.patches[min(self.patch_index, len(self.patches) - 1)]
            self.patch_index += 1
            return patch
        if state is WorkflowState.ANALYZE_FAILURES:
            signature = payload.get("failure_signature")
            return {
                "analysis": "validation failed",
                "failure_signature": signature if isinstance(signature, str) else "unknown",
            }
        if state is WorkflowState.REVIEW_DIFF:
            return {"summary": "diff reviewed", "approved": True}
        raise AssertionError(f"unexpected model state: {state}")


class WorkflowSandboxRunner:
    def run(self, spec: SandboxRunSpec) -> SandboxResult:
        output = SandboxResult(
            command=spec.command,
            normalized_command=spec.command,
            category=SandboxCommandCategory.TESTS,
            exit_code=0,
            stdout="passed",
            duration_ms=10,
            network_enabled=spec.network_enabled,
        )
        if "--bad-option" in spec.command:
            output.exit_code = 4
            output.stdout = ""
            output.stderr = "pytest: error: unrecognized arguments: --bad-option"
            return output
        source = (spec.workspace_path / "calculator.py").read_text(encoding="utf-8")
        if "return a + b" not in source:
            output.exit_code = 1
            output.stdout = "assert add(2, 3) == 5"
        return output


def create_workflow_run(session: Session, workspace: Path) -> tuple[str, str]:
    service = RunService(session)
    user = service.create_user(
        email=f"{workspace.name}@workflow.test",
        display_name="Workflow User",
    )
    repository = service.register_repository(
        name=f"repo-{workspace.name}",
        local_path=str(workspace),
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Fix calculator",
        description="Fix add implementation",
    )
    run = service.create_agent_run(task_id=task.id, base_branch="feature/workflow")
    return user.id, run.id


def make_calculator_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )
    (workspace / "test_calculator.py").write_text(
        "from calculator import add\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "local@example.test"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Local User"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace


def build_workflow(
    *,
    session: Session,
    workspace: Path,
    model: ScriptedWorkflowModel,
    permission_level: PermissionLevel = PermissionLevel.SANDBOX_COMMANDS,
    validation_command: tuple[str, ...] | None = (
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "test_calculator.py",
    ),
) -> DeterministicCodingAgentWorkflow:
    user_id, run_id = create_workflow_run(session, workspace)
    indexer = RepoIndexer(embedder=WorkflowEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(workspace)
    retrieval = RetrievalEngine(indexer=indexer, snapshot=snapshot)
    policy = PolicyEngine(
        PolicyConfig(
            workspace_path=workspace,
            permission_level=permission_level,
            allowed_commands=((sys.executable, "-B", "-m", "pytest"), ("pytest",)),
        ),
        session=session,
    )
    return DeterministicCodingAgentWorkflow(
        session=session,
        model=model,
        policy=policy,
        workspace_path=workspace,
        agent_run_id=run_id,
        actor_user_id=user_id,
        indexer=indexer,
        retrieval_engine=retrieval,
        sandbox_runner=WorkflowSandboxRunner(),
        config=WorkflowConfig(
            validation_command=validation_command,
            validation_timeout_seconds=30,
        ),
    )


def test_workflow_runs_full_retry_path_and_records_every_state(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_calculator_workspace(tmp_path)
    model = ScriptedWorkflowModel(
        [
            {
                "path": "calculator.py",
                "original_text": "return a - b",
                "replacement_text": "return a * b",
            },
            {
                "path": "calculator.py",
                "original_text": "return a * b",
                "replacement_text": "return a + b",
            },
        ]
    )
    workflow = build_workflow(session=session, workspace=workspace, model=model)

    result = workflow.run(WorkflowInput(task="Fix add in calculator.py"))

    assert result.status is WorkflowStatus.WAITING_APPROVAL
    assert result.patch_attempts == 1
    assert result.validation_runs == 0
    assert result.final_report.approval_required is True
    assert result.final_report.tests_ran is False
    assert result.final_report.files_changed == ["calculator.py"]
    assert result.final_report.files_cited
    assert "return a - b" in (workspace / "calculator.py").read_text(encoding="utf-8")

    expected_states = {
        WorkflowState.INTAKE,
        WorkflowState.CLASSIFY_TASK,
        WorkflowState.RETRIEVE_CONTEXT,
        WorkflowState.DRAFT_PLAN,
        WorkflowState.RISK_ASSESSMENT,
        WorkflowState.APPROVAL_IF_NEEDED,
        WorkflowState.GENERATE_PATCH,
        WorkflowState.APPLY_PATCH_WORKSPACE,
        WorkflowState.FINAL_REPORT,
    }
    assert expected_states <= set(result.states)

    steps = session.execute(
        select(AgentStep).where(AgentStep.agent_run_id == workflow.agent_run_id)
    ).scalars()
    recorded_step_names = {step.name for step in steps}
    assert {state.value for state in expected_states} <= recorded_step_names

    model_audits = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.agent_run_id == workflow.agent_run_id,
                AuditEvent.event_type == "model.call",
            )
        )
        .scalars()
        .all()
    )
    tool_calls = (
        session.execute(
            select(ToolCall).join(AgentStep).where(AgentStep.agent_run_id == workflow.agent_run_id)
        )
        .scalars()
        .all()
    )
    assert len(model_audits) >= MIN_MODEL_AUDITS
    assert {call.tool_name for call in tool_calls} >= {
        "retrieve_context",
        "propose_patch",
        "apply_patch_to_workspace",
    }


def test_workflow_stops_on_repeated_validation_failure(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_calculator_workspace(tmp_path)
    model = ScriptedWorkflowModel(
        [
            {
                "path": "calculator.py",
                "original_text": "return a - b",
                "replacement_text": "return a + b",
            },
            {
                "path": "calculator.py",
                "original_text": "return a + b",
                "replacement_text": "return a * b",
            },
        ]
    )
    workflow = build_workflow(
        session=session,
        workspace=workspace,
        model=model,
        validation_command=(sys.executable, "-B", "-m", "pytest", "--bad-option"),
    )

    result = workflow.run(WorkflowInput(task="Fix add in calculator.py"))

    assert result.status is WorkflowStatus.WAITING_APPROVAL
    assert result.patch_attempts == 1
    assert result.validation_runs == 0
    assert result.final_report.stop_reason is WorkflowStopReason.APPROVAL_REQUIRED
    assert result.final_report.tests_ran is False
    assert result.final_report.tests_passed is None


def test_workflow_stops_for_approval_before_workspace_write(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_calculator_workspace(tmp_path)
    model = ScriptedWorkflowModel(
        [
            {
                "path": "calculator.py",
                "original_text": "return a - b",
                "replacement_text": "return a + b",
            }
        ]
    )
    workflow = build_workflow(
        session=session,
        workspace=workspace,
        model=model,
        permission_level=PermissionLevel.PROPOSE_PATCH,
    )

    result = workflow.run(WorkflowInput(task="Fix add in calculator.py"))

    assert result.status is WorkflowStatus.WAITING_APPROVAL
    assert result.patch_attempts == 0
    assert result.final_report.approval_required is True
    assert result.final_report.tests_ran is False
    assert "return a - b" in (workspace / "calculator.py").read_text(encoding="utf-8")

    run = RunService(session).runs.get(workflow.agent_run_id)
    assert run is not None
    assert AgentRunStatus(run.status) is AgentRunStatus.WAITING_APPROVAL
    tool_calls = (
        session.execute(
            select(ToolCall).join(AgentStep).where(AgentStep.agent_run_id == workflow.agent_run_id)
        )
        .scalars()
        .all()
    )
    assert {call.tool_name for call in tool_calls} >= {"retrieve_context", "request_approval"}
