from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, PolicyDecision
from app.models.enums import PolicyDecisionResult
from app.security import (
    PermissionLevel,
    PolicyConfig,
    PolicyEngine,
    PolicyOperation,
    PolicyRequest,
    PolicyViolation,
)
from app.services.runs import RunService


def make_config(tmp_path: Path, level: PermissionLevel) -> PolicyConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return PolicyConfig(workspace_path=workspace, permission_level=level)


def create_agent_run(session: Session) -> str:
    service = RunService(session)
    user = service.create_user(email="policy@example.test", display_name="Policy User")
    repository = service.register_repository(
        name="switch",
        local_path="/workspace/switch",
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Policy test",
        description="Exercise policy decisions",
    )
    run = service.create_agent_run(task_id=task.id, base_branch="feature/policy")
    return run.id


def test_dangerous_shell_commands_are_denied(tmp_path: Path) -> None:
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.SANDBOX_COMMANDS))

    evaluation = engine.evaluate(
        PolicyRequest(
            operation=PolicyOperation.RUN_COMMAND,
            command=("bash", "-lc", "rm -rf /"),
        )
    )

    assert evaluation.decision is PolicyDecisionResult.DENIED
    assert "shell" in evaluation.reason


def test_allowed_validation_command_is_permitted(tmp_path: Path) -> None:
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.SANDBOX_COMMANDS))

    evaluation = engine.evaluate(
        PolicyRequest(
            operation=PolicyOperation.RUN_COMMAND,
            command=("pytest", "tests/test_policy_engine.py"),
        )
    )

    assert evaluation.decision is PolicyDecisionResult.ALLOWED


def test_commands_must_run_in_sandbox(tmp_path: Path) -> None:
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.SANDBOX_COMMANDS))

    evaluation = engine.evaluate(
        PolicyRequest(
            operation=PolicyOperation.RUN_COMMAND,
            command=("pytest",),
            requires_sandbox=False,
        )
    )

    assert evaluation.decision is PolicyDecisionResult.DENIED
    assert "sandbox" in evaluation.reason


def test_writes_outside_workspace_are_denied(tmp_path: Path) -> None:
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.WRITE_WORKSPACE))

    evaluation = engine.evaluate(
        PolicyRequest(operation=PolicyOperation.WRITE_FILE, path=Path("/etc/passwd"))
    )

    assert evaluation.decision is PolicyDecisionResult.DENIED
    assert "outside" in evaluation.reason


def test_secret_and_policy_file_writes_are_denied(tmp_path: Path) -> None:
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.WRITE_WORKSPACE))

    secret = engine.evaluate(PolicyRequest(operation=PolicyOperation.WRITE_FILE, path=Path(".env")))
    policy = engine.evaluate(
        PolicyRequest(operation=PolicyOperation.WRITE_FILE, path=Path("app/security/policy.py"))
    )

    assert secret.decision is PolicyDecisionResult.DENIED
    assert policy.decision is PolicyDecisionResult.DENIED
    assert "policy" in policy.reason


def test_protected_branch_write_is_denied(tmp_path: Path) -> None:
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.WRITE_WORKSPACE))

    evaluation = engine.evaluate(
        PolicyRequest(
            operation=PolicyOperation.WRITE_FILE,
            path=Path("app/main.py"),
            branch="main",
        )
    )

    assert evaluation.decision is PolicyDecisionResult.DENIED
    assert "protected branch" in evaluation.reason


def test_branch_artifacts_require_human_approval(tmp_path: Path) -> None:
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.BRANCH_ARTIFACT))

    pending = engine.evaluate(
        PolicyRequest(operation=PolicyOperation.CREATE_BRANCH_ARTIFACT, branch="feature/local")
    )
    approved = engine.evaluate(
        PolicyRequest(
            operation=PolicyOperation.CREATE_BRANCH_ARTIFACT,
            branch="feature/local",
            human_approved=True,
        )
    )

    assert pending.decision is PolicyDecisionResult.REQUIRES_APPROVAL
    assert pending.approval_required is True
    assert approved.decision is PolicyDecisionResult.ALLOWED


def test_insufficient_level_and_admin_reserved_are_denied(tmp_path: Path) -> None:
    low = PolicyEngine(make_config(tmp_path, PermissionLevel.PLAN_ONLY))
    admin = PolicyEngine(make_config(tmp_path, PermissionLevel.ADMIN_RESERVED))

    write = low.evaluate(
        PolicyRequest(operation=PolicyOperation.WRITE_FILE, path=Path("app/main.py"))
    )
    read = admin.evaluate(
        PolicyRequest(operation=PolicyOperation.READ_PATH, path=Path("app/main.py"))
    )

    assert write.decision is PolicyDecisionResult.DENIED
    assert "requires level" in write.reason
    assert read.decision is PolicyDecisionResult.DENIED
    assert "reserved" in read.reason


def test_policy_decisions_are_persisted_and_audited(
    tmp_path: Path,
    session: Session,
) -> None:
    run_id = create_agent_run(session)
    engine = PolicyEngine(make_config(tmp_path, PermissionLevel.SANDBOX_COMMANDS), session=session)

    engine.assert_allowed(
        PolicyRequest(
            operation=PolicyOperation.RUN_COMMAND,
            command=("pytest",),
            agent_run_id=run_id,
        )
    )
    with pytest.raises(PolicyViolation):
        engine.assert_allowed(
            PolicyRequest(
                operation=PolicyOperation.RUN_COMMAND,
                command=("rm", "-rf", "."),
                agent_run_id=run_id,
            )
        )

    decisions = (
        session.execute(select(PolicyDecision).where(PolicyDecision.agent_run_id == run_id))
        .scalars()
        .all()
    )
    audits = (
        session.execute(select(AuditEvent).where(AuditEvent.agent_run_id == run_id)).scalars().all()
    )

    assert [decision.decision for decision in decisions[-2:]] == [
        PolicyDecisionResult.ALLOWED,
        PolicyDecisionResult.DENIED,
    ]
    assert any(event.event_type == "policy.evaluated" for event in audits)
