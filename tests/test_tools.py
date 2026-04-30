import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indexing import InMemoryVectorStore, RepoIndexer
from app.models.entities import AuditEvent, ToolCall, ValidationRun
from app.models.enums import ApprovalStatus
from app.retrieval import RetrievalEngine
from app.sandbox import SandboxResult, SandboxRunSpec
from app.sandbox.types import SandboxCommandCategory
from app.security import PermissionLevel, PolicyConfig, PolicyEngine
from app.services.runs import RunService
from app.tools import ToolContext, ToolRegistry
from app.tools.schemas import (
    ApplyPatchInput,
    CreateBranchArtifactInput,
    GetGitDiffInput,
    ListFilesInput,
    ProposePatchInput,
    ReadFileInput,
    RequestApprovalInput,
    RetrieveContextInput,
    RunValidationCommandInput,
    SearchSymbolsInput,
    SearchTextInput,
    SummarizeDiffInput,
)


class ToolEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float("auth" in text.lower()),
                float("token" in text.lower()),
                float("test" in text.lower()),
            ]
            for text in texts
        ]


class FakeSandboxRunner:
    def run(self, spec: SandboxRunSpec) -> SandboxResult:
        if spec.command[:1] == ("pytest",):
            return SandboxResult(
                command=spec.command,
                normalized_command=spec.command,
                category=SandboxCommandCategory.TESTS,
                exit_code=0,
                stdout="pytest 9.0.3",
                duration_ms=5,
                network_enabled=spec.network_enabled,
            )
        return SandboxResult(
            command=spec.command,
            normalized_command=spec.command,
            category=SandboxCommandCategory.TESTS,
            exit_code=1,
            stderr="failed",
            duration_ms=5,
            network_enabled=spec.network_enabled,
        )


def create_run(session: Session, workspace: Path) -> tuple[str, str, str]:
    service = RunService(session)
    user = service.create_user(email=f"{workspace.name}@example.test", display_name="Tool User")
    repository = service.register_repository(
        name=f"repo-{workspace.name}",
        local_path=str(workspace),
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Tool test",
        description="Exercise tool layer",
    )
    run = service.create_agent_run(task_id=task.id, base_branch="feature/tools")
    step = service.create_step(agent_run_id=run.id, sequence=1, name="tools")
    return user.id, run.id, step.id


def make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "auth.py").write_text(
        "def validate_token(token: str) -> bool:\n    return bool(token)\n",
        encoding="utf-8",
    )
    (workspace / "test_auth.py").write_text(
        "from auth import validate_token\n\n"
        "def test_validate_token() -> None:\n"
        "    assert validate_token('x')\n",
        encoding="utf-8",
    )
    (workspace / ".env").write_text("TOKEN=super-secret\n", encoding="utf-8")
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


def make_tools(
    session: Session,
    workspace: Path,
    level: PermissionLevel = PermissionLevel.BRANCH_ARTIFACT,
) -> ToolRegistry:
    user_id, run_id, step_id = create_run(session, workspace)
    context = ToolContext(
        agent_run_id=run_id,
        agent_step_id=step_id,
        actor_user_id=user_id,
        workspace_path=workspace,
    )
    policy = PolicyEngine(
        PolicyConfig(workspace_path=workspace, permission_level=level),
        session=session,
    )
    indexer = RepoIndexer(embedder=ToolEmbedder(), vector_store=InMemoryVectorStore())
    snapshot = indexer.index(workspace)
    retrieval = RetrievalEngine(indexer=indexer, snapshot=snapshot)
    return ToolRegistry(
        session=session,
        policy=policy,
        context=context,
        indexer=indexer,
        retrieval_engine=retrieval,
        sandbox_runner=FakeSandboxRunner(),
    )


def approve_for(tools: ToolRegistry, action: str) -> str:
    service = RunService(tools.session)
    approval = service.request_approval(
        agent_run_id=tools.context.agent_run_id,
        requested_by_user_id=tools.context.actor_user_id or "",
        requested_action=action,
        risk_level="high",
        reason=f"Approve {action}",
    )
    decided = service.decide_approval(
        approval_request_id=approval.id,
        decided_by_user_id=tools.context.actor_user_id or "",
        status=ApprovalStatus.APPROVED,
        decision_note="approved",
    )
    return decided.id


def assert_tool_audited(session: Session, run_id: str, tool_name: str) -> None:
    calls = session.execute(select(ToolCall).where(ToolCall.tool_name == tool_name)).scalars().all()
    audits = (
        session.execute(select(AuditEvent).where(AuditEvent.agent_run_id == run_id)).scalars().all()
    )
    assert calls
    assert any(event.event_type == "tool.executed" for event in audits)


def assert_tools_audited(session: Session, run_id: str, tool_names: set[str]) -> None:
    calls = session.execute(select(ToolCall)).scalars().all()
    recorded = {call.tool_name for call in calls}
    audits = (
        session.execute(select(AuditEvent).where(AuditEvent.agent_run_id == run_id)).scalars().all()
    )
    assert tool_names <= recorded
    assert sum(1 for event in audits if event.event_type == "tool.executed") >= len(tool_names)


def test_read_list_search_retrieve_tools_are_compact_and_audited(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_workspace(tmp_path)
    tools = make_tools(session, workspace)

    read = tools.read_file(ReadFileInput(path=Path("auth.py")))
    listed = tools.list_files(ListFilesInput())
    text = tools.search_text(SearchTextInput(query="validate_token"))
    symbols = tools.search_symbols(SearchSymbolsInput(query="validate"))
    context = tools.retrieve_context(RetrieveContextInput(query="auth token"))

    assert read.success and "validate_token" in read.text
    assert listed.success and "auth.py" in listed.files
    assert ".env" not in listed.files
    assert text.success and text.matches
    assert symbols.success and symbols.symbols
    assert context.success and context.bundles
    assert_tools_audited(
        session,
        tools.context.agent_run_id,
        {"read_file", "list_files", "search_text", "search_symbols", "retrieve_context"},
    )


def test_policy_denial_returns_structured_error_and_records_tool_call(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_workspace(tmp_path)
    tools = make_tools(session, workspace, level=PermissionLevel.READ_ONLY_QA)

    output = tools.apply_patch_to_workspace(
        ApplyPatchInput(
            path=Path("auth.py"),
            original_text="return bool(token)",
            replacement_text="return token == 'x'",
        )
    )

    assert output.success is False
    assert output.error is not None
    assert output.error.code == "policy_denied"
    assert "requires level" in output.error.message
    assert "return bool(token)" in (workspace / "auth.py").read_text(encoding="utf-8")
    assert_tool_audited(session, tools.context.agent_run_id, "apply_patch_to_workspace")


def test_patch_diff_apply_git_diff_and_summarize(tmp_path: Path, session: Session) -> None:
    workspace = make_workspace(tmp_path)
    tools = make_tools(session, workspace)

    proposed = tools.propose_patch(
        ProposePatchInput(
            path=Path("auth.py"),
            original_text="return bool(token)\n",
            replacement_text="return token == 'x'\n",
        )
    )
    export_approval_id = approve_for(tools, "export_patch")
    proposed = tools.propose_patch(
        ProposePatchInput(
            path=Path("auth.py"),
            original_text="return bool(token)\n",
            replacement_text="return token == 'x'\n",
            approval_request_id=export_approval_id,
        )
    )
    apply_approval_id = approve_for(tools, "apply_patch")
    applied = tools.apply_patch_to_workspace(
        ApplyPatchInput(
            path=Path("auth.py"),
            original_text="return bool(token)",
            replacement_text="return token == 'x'",
            branch="feature/tools",
            approval_request_id=apply_approval_id,
        )
    )
    diff = tools.get_git_diff(GetGitDiffInput(path=Path("auth.py")))
    summary = tools.summarize_diff(SummarizeDiffInput(diff=diff.diff))

    assert proposed.success and "--- a/auth.py" in proposed.diff
    assert proposed.approval_required
    assert applied.success and applied.changed
    assert diff.success and "return token == 'x'" in diff.diff
    assert summary.success and summary.total_added >= 1
    assert_tools_audited(
        session,
        tools.context.agent_run_id,
        {"propose_patch", "apply_patch_to_workspace", "get_git_diff", "summarize_diff"},
    )


def test_validation_command_allowlist_and_dangerous_command_denial(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_workspace(tmp_path)
    tools = make_tools(session, workspace)

    allowed = tools.run_validation_command(
        RunValidationCommandInput(
            command=("pytest", "--version"),
            approval_request_id=approve_for(tools, "run_validation"),
            read_only_workspace=False,
        )
    )
    denied = tools.run_validation_command(
        RunValidationCommandInput(command=("bash", "-lc", "echo bad"))
    )

    assert allowed.success
    assert allowed.exit_code == 0
    assert allowed.validation_run_id is not None
    assert allowed.category == "tests"
    validation = session.get(ValidationRun, allowed.validation_run_id)
    assert validation is not None
    assert validation.exit_code == 0
    assert validation.output_summary is not None
    assert denied.success is False
    assert denied.error is not None
    assert denied.error.code == "policy_denied"
    assert_tool_audited(session, tools.context.agent_run_id, "run_validation_command")


def test_approval_and_branch_artifact_tools(tmp_path: Path, session: Session) -> None:
    workspace = make_workspace(tmp_path)
    tools = make_tools(session, workspace)

    approval = tools.request_approval(RequestApprovalInput(reason="Need branch artifact"))
    pending = tools.create_branch_artifact(
        CreateBranchArtifactInput(branch_name="feature/tools", summary="patch ready")
    )
    approved = tools.create_branch_artifact(
        CreateBranchArtifactInput(
            branch_name="feature/tools",
            summary="patch ready",
            approval_request_id=approve_for(tools, "create_branch_artifact"),
        )
    )

    assert approval.success and approval.approval_request_id
    assert pending.success is False
    assert pending.error is not None
    assert pending.error.code == "approval_required"
    assert approved.success
    assert approved.artifact_path is not None
    assert_tools_audited(
        session,
        tools.context.agent_run_id,
        {"request_approval", "create_branch_artifact"},
    )
