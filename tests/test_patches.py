import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, PatchArtifact
from app.patches import PatchRejected, PatchService
from app.patches.types import PatchRiskCategory
from app.services.runs import RunService

MIN_EXPECTED_ARTIFACTS = 2


def create_patch_run(session: Session, workspace: Path) -> tuple[str, str]:
    service = RunService(session)
    user = service.create_user(
        email=f"{workspace.name}@patch.test",
        display_name="Patch User",
    )
    repository = service.register_repository(
        name=f"repo-{workspace.name}",
        local_path=str(workspace),
        default_branch="main",
    )
    task = service.create_task(
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Patch task",
        description="Exercise patch system",
    )
    run = service.create_agent_run(task_id=task.id, base_branch="feature/patches")
    return user.id, run.id


def make_patch_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "math.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )
    (workspace / "app" / "security").mkdir(parents=True)
    (workspace / "app" / "security" / "policy.py").write_text(
        "ALLOW = False\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    return workspace


def make_service(session: Session, workspace: Path) -> PatchService:
    user_id, run_id = create_patch_run(session, workspace)
    return PatchService(
        session=session,
        workspace_path=workspace,
        agent_run_id=run_id,
        actor_user_id=user_id,
    )


def test_safe_patch_applies_stores_artifacts_and_generates_rollback(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_patch_workspace(tmp_path)
    service = make_service(session, workspace)
    original = "def add(a: int, b: int) -> int:\n    return a - b\n"
    replacement = "def add(a: int, b: int) -> int:\n    return a + b\n"

    diff = service.generate_unified_diff(Path("src/math.py"), original, replacement)
    result = service.apply_patch(diff=diff)

    assert result.applied
    assert result.metadata.changed_files == ["src/math.py"]
    assert result.metadata.added_files == []
    assert result.metadata.deleted_files == []
    assert result.rollback_patch
    assert "return a - b" in result.rollback_patch
    assert "return a + b" in (workspace / "src" / "math.py").read_text(encoding="utf-8")

    artifacts = session.execute(select(PatchArtifact)).scalars().all()
    events = (
        session.execute(select(AuditEvent).where(AuditEvent.agent_run_id == service.agent_run_id))
        .scalars()
        .all()
    )
    assert len(artifacts) >= MIN_EXPECTED_ARTIFACTS
    assert {event.event_type for event in events} >= {
        "patch.artifact_stored",
        "patch.applied",
        "patch.rollback_generated",
    }


def test_malicious_path_patch_is_rejected_and_audited(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_patch_workspace(tmp_path)
    service = make_service(session, workspace)
    diff = "--- a/../escape.py\n+++ b/../escape.py\n@@ -1 +1 @@\n-old\n+new\n"

    with pytest.raises(PatchRejected, match="escapes workspace"):
        service.analyze_diff(diff)

    events = (
        session.execute(select(AuditEvent).where(AuditEvent.agent_run_id == service.agent_run_id))
        .scalars()
        .all()
    )
    assert any(event.event_type == "patch.rejected" for event in events)


def test_high_risk_file_requires_human_approval(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_patch_workspace(tmp_path)
    service = make_service(session, workspace)
    original = "ALLOW = False\n"
    replacement = "ALLOW = True\n"
    diff = service.generate_unified_diff(Path("app/security/policy.py"), original, replacement)

    metadata = service.analyze_diff(diff)

    assert metadata.approval_required
    assert PatchRiskCategory.AUTH_SECURITY in metadata.high_risk_categories
    assert PatchRiskCategory.PERMISSION_POLICY in metadata.high_risk_categories
    with pytest.raises(PatchRejected, match="requires human approval"):
        service.apply_patch(diff=diff)
    assert "ALLOW = False" in (workspace / "app" / "security" / "policy.py").read_text(
        encoding="utf-8"
    )

    approved = service.apply_patch(diff=diff, human_approved=True)
    assert approved.applied
    assert approved.metadata.approval_required
    assert "ALLOW = True" in (workspace / "app" / "security" / "policy.py").read_text(
        encoding="utf-8"
    )


def test_added_and_deleted_files_are_tracked(
    tmp_path: Path,
    session: Session,
) -> None:
    workspace = make_patch_workspace(tmp_path)
    service = make_service(session, workspace)
    diff = (
        "--- /dev/null\n"
        "+++ b/src/new_module.py\n"
        "@@ -0,0 +1 @@\n"
        "+VALUE = 1\n"
        "--- a/src/math.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-def add(a: int, b: int) -> int:\n"
        "-    return a - b\n"
    )

    result = service.apply_patch(diff=diff)

    assert result.metadata.added_files == ["src/new_module.py"]
    assert result.metadata.deleted_files == ["src/math.py"]
    assert (workspace / "src" / "new_module.py").exists()
    assert not (workspace / "src" / "math.py").exists()
