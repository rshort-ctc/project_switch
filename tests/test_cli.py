from collections.abc import Callable
from typing import Any

from typer.testing import CliRunner

from app import cli
from app.cli import app

runner = CliRunner()


def test_repo_add_calls_backend(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        api_url: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((method, path, json_body))
        return {
            "id": "repo-1",
            "name": "demo",
            "local_path": "/tmp/demo",
            "default_branch": "main",
            "is_active": True,
        }

    monkeypatch.setattr(cli, "request_json", fake_request)

    result = runner.invoke(app, ["repo", "add", "/tmp/demo", "--name", "demo"])

    assert result.exit_code == 0
    assert calls == [
        (
            "POST",
            "/repos",
            {"name": "demo", "local_path": "/tmp/demo", "default_branch": "main"},
        )
    ]
    assert "repo-1 demo /tmp/demo" in result.output


def test_repo_index_json_output(monkeypatch) -> None:
    monkeypatch.setattr(cli, "request_json", _fake_request({"index_id": "idx-1"}))

    result = runner.invoke(app, ["repo", "index", "repo-1", "--json"])

    assert result.exit_code == 0
    assert '"index_id": "idx-1"' in result.output


def test_ask_displays_answer_degraded_warning_and_citations(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "request_json",
        _fake_request(
            {
                "question": "Where is approval handled?",
                "answer": "Approval is handled in app/api/routes/approvals.py.",
                "used_model": False,
                "degraded": True,
                "degraded_reason": "model unavailable",
                "index_id": "idx-1",
                "retrieval_summary": {
                    "total_bundles": 1,
                    "lanes_used": ["semantic"],
                    "total_estimated_tokens": 24,
                },
                "contexts": [
                    {
                        "path": "app/api/routes/approvals.py",
                        "start_line": 10,
                        "end_line": 30,
                        "score": 91.0,
                        "lanes": ["semantic"],
                        "reasons": ["semantic vector similarity"],
                    }
                ],
            }
        ),
    )

    result = runner.invoke(app, ["ask", "repo-1", "Where is approval handled?"])

    assert result.exit_code == 0
    assert "answer:" in result.output
    assert "degraded: model unavailable" in result.output
    assert "lanes: semantic" in result.output
    assert "app/api/routes/approvals.py:10-30" in result.output


def test_ask_unindexed_repo_error_is_helpful(monkeypatch) -> None:
    def fake_request(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise cli.typer.BadParameter(
            "Repository is not indexed. Run POST /repos/{repository_id}/index or "
            "`switch repo index <repo-id>` first."
        )

    monkeypatch.setattr(cli, "request_json", fake_request)

    result = runner.invoke(app, ["ask", "repo-1", "Where is approval handled?"])

    assert result.exit_code != 0
    assert "switch repo index" in result.output


def test_task_create_calls_backend(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        api_url: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((method, path, json_body))
        return {
            "task": {"id": "task-1", "status": "pending"},
            "run": {"id": "run-1", "status": "pending"},
        }

    monkeypatch.setattr(cli, "request_json", fake_request)

    result = runner.invoke(
        app,
        [
            "task",
            "create",
            "repo-1",
            "Fix bug",
            "--description",
            "details",
            "--created-by",
            "user-1",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "POST",
            "/tasks",
            {
                "repository_id": "repo-1",
                "created_by_user_id": "user-1",
                "title": "Fix bug",
                "description": "details",
            },
        )
    ]
    assert "task: task-1 pending" in result.output


def test_task_run_calls_backend(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        api_url: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((method, path, json_body))
        return {
            "task_id": "task-1",
            "agent_run_id": "run-1",
            "status": "queued",
            "message": "Agent workflow started.",
            "status_url": "/tasks/task-1",
        }

    monkeypatch.setattr(cli, "request_json", fake_request)

    result = runner.invoke(app, ["task", "run", "task-1", "--actor-user-id", "user-1"])

    assert result.exit_code == 0
    assert calls == [
        (
            "POST",
            "/tasks/task-1/run",
            {"actor_user_id": "user-1"},
        )
    ]
    assert "run: run-1" in result.output
    assert "status url: /tasks/task-1" in result.output


def test_task_diff_displays_changed_files(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "request_json",
        _fake_request({"task_id": "task-1", "changed_files": ["app/main.py"], "diff": ""}),
    )

    result = runner.invoke(app, ["task", "diff", "task-1"])

    assert result.exit_code == 0
    assert "app/main.py" in result.output


def test_approve_and_deny_call_backend(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(
        method: str,
        path: str,
        *,
        api_url: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((method, path, json_body))
        return {
            "id": path.split("/")[2],
            "status": "approved" if path.endswith("/approve") else "rejected",
            "requested_action": "run_validation",
            "risk_level": "medium",
        }

    monkeypatch.setattr(cli, "request_json", fake_request)

    approve_result = runner.invoke(app, ["approve", "approval-1", "--user", "user-1"])
    deny_result = runner.invoke(app, ["deny", "approval-2", "--user", "user-1", "--note", "no"])

    assert approve_result.exit_code == 0
    assert deny_result.exit_code == 0
    assert calls == [
        (
            "POST",
            "/approvals/approval-1/approve",
            {"decided_by_user_id": "user-1", "decision_note": None},
        ),
        (
            "POST",
            "/approvals/approval-2/deny",
            {"decided_by_user_id": "user-1", "decision_note": "no"},
        ),
    ]


def test_local_only_blocks_non_local_backend() -> None:
    result = runner.invoke(app, ["agent", "health", "--api-url", "https://example.com"])

    assert result.exit_code != 0
    assert "LOCAL_ONLY blocks non-local API endpoints" in result.output


def _fake_request(extra: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    def fake_request(
        method: str,
        path: str,
        *,
        api_url: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "status": "ready",
            "repository_id": "repo-1",
            "indexed_files": 1,
            "indexed_chunks": 1,
            "skipped_ignored_files": 0,
            "skipped_binary_files": 0,
            "skipped_unchanged_files": 0,
        }
        payload.update(extra)
        return payload

    return fake_request
