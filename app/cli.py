import json
from typing import Annotated, Any
from urllib.parse import urljoin, urlparse

import httpx
import typer

from app.core.config import Settings
from app.security.redaction import redact_secrets

DEFAULT_API_URL = "http://127.0.0.1:8000"
HTTP_ERROR_STATUS = 400

app = typer.Typer(help="SWITCH local coding agent CLI", no_args_is_help=True)
agent_app = typer.Typer(help="Inspect local agent backend state", no_args_is_help=True)
repo_app = typer.Typer(help="Register and index repositories", no_args_is_help=True)
task_app = typer.Typer(help="Create and inspect coding tasks", no_args_is_help=True)
validation_app = typer.Typer(help="Inspect validation results", no_args_is_help=True)

app.add_typer(agent_app, name="agent")
app.add_typer(repo_app, name="repo")
app.add_typer(task_app, name="task")
app.add_typer(validation_app, name="validation")

ApiUrlOption = Annotated[
    str,
    typer.Option(
        "--api-url",
        envvar="SWITCH_API_URL",
        help="Local backend API URL.",
    ),
]
JsonOption = Annotated[bool, typer.Option("--json", help="Print JSON output.")]


@agent_app.command("health")
def agent_health(
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", "/health/details", api_url=api_url)
    emit(payload, json_output=json_output, lines=_health_lines(payload))


@agent_app.command("models")
def agent_models(
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", "/agent/models", api_url=api_url)
    lines = [f"{role}: {model or 'not configured'}" for role, model in payload.items()]
    emit(payload, json_output=json_output, lines=lines)


@repo_app.command("add")
def repo_add(
    path: str,
    name: Annotated[str | None, typer.Option("--name", help="Repository display name.")] = None,
    default_branch: Annotated[str, typer.Option("--default-branch")] = "main",
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    body = {
        "name": name or path.rstrip("/").split("/")[-1],
        "local_path": path,
        "default_branch": default_branch,
    }
    payload = request_json("POST", "/repos", api_url=api_url, json_body=body)
    emit(payload, json_output=json_output, lines=[_repo_line(payload)])


@repo_app.command("list")
def repo_list(
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", "/repos", api_url=api_url)
    repositories = payload.get("repositories", [])
    emit(payload, json_output=json_output, lines=[_repo_line(repo) for repo in repositories])


@repo_app.command("index")
def repo_index(
    repository_id: str,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("POST", f"/repos/{repository_id}/index", api_url=api_url)
    lines = [
        f"index: {payload['index_id']}",
        f"status: {payload['status']}",
        f"files: {payload['indexed_files']}",
        f"chunks: {payload['indexed_chunks']}",
    ]
    emit(payload, json_output=json_output, lines=lines)


@repo_app.command("status")
def repo_status(
    repository_id: str,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", f"/repos/{repository_id}/status", api_url=api_url)
    repository = payload["repository"]
    lines = [_repo_line(repository)]
    latest = payload.get("latest_index")
    if latest is not None:
        lines.extend([f"index: {latest['index_id']}", f"index status: {latest['status']}"])
    emit(payload, json_output=json_output, lines=lines)


@app.command("ask")
def ask(
    repository_id: str,
    question: str,
    max_bundles: Annotated[int, typer.Option("--max-bundles", min=1, max=20)] = 5,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json(
        "POST",
        "/ask",
        api_url=api_url,
        json_body={
            "repository_id": repository_id,
            "question": question,
            "max_bundles": max_bundles,
        },
    )
    lines = [payload["answer"]]
    lines.extend(
        f"{context['path']}:{context['start_line']}-{context['end_line']} "
        f"score={context['score']:.2f}"
        for context in payload.get("contexts", [])
    )
    emit(payload, json_output=json_output, lines=lines)


@task_app.command("create")
def task_create(
    repository_id: str,
    title: str,
    description: Annotated[str, typer.Option("--description", "-d")] = "",
    created_by: Annotated[
        str, typer.Option("--created-by", help="Local user id creating the task.")
    ] = "",
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    if not created_by:
        raise typer.BadParameter("--created-by is required")
    payload = request_json(
        "POST",
        "/tasks",
        api_url=api_url,
        json_body={
            "repository_id": repository_id,
            "created_by_user_id": created_by,
            "title": title,
            "description": description,
        },
    )
    task = payload["task"]
    run = payload["run"]
    emit(
        payload,
        json_output=json_output,
        lines=[f"task: {task['id']} {task['status']}", f"run: {run['id']} {run['status']}"],
    )


@task_app.command("status")
def task_status(
    task_id: str,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", f"/tasks/{task_id}", api_url=api_url)
    task = payload["task"]
    lines = [f"task: {task['id']} {task['status']} {task['title']}"]
    if payload.get("run") is not None:
        run = payload["run"]
        lines.append(f"run: {run['id']} {run['status']}")
    emit(payload, json_output=json_output, lines=lines)


@task_app.command("logs")
def task_logs(
    task_id: str,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", f"/tasks/{task_id}/logs", api_url=api_url)
    lines = [
        f"{event['created_at']} {event['event_type']} {event['summary']}"
        for event in payload.get("events", [])
    ]
    emit(payload, json_output=json_output, lines=lines)


@task_app.command("diff")
def task_diff(
    task_id: str,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", f"/tasks/{task_id}/diff", api_url=api_url)
    lines = ["changed files:"]
    lines.extend(f"  {path}" for path in payload.get("changed_files", []))
    if payload.get("diff"):
        lines.extend(["", payload["diff"]])
    emit(payload, json_output=json_output, lines=lines)


@app.command("approve")
def approve(
    approval_id: str,
    user: Annotated[str, typer.Option("--user", help="Approving local user id.")],
    note: Annotated[str | None, typer.Option("--note")] = None,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json(
        "POST",
        f"/approvals/{approval_id}/approve",
        api_url=api_url,
        json_body={"decided_by_user_id": user, "decision_note": note},
    )
    emit(payload, json_output=json_output, lines=[_approval_line(payload)])


@app.command("deny")
def deny(
    approval_id: str,
    user: Annotated[str, typer.Option("--user", help="Denying local user id.")],
    note: Annotated[str | None, typer.Option("--note")] = None,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json(
        "POST",
        f"/approvals/{approval_id}/deny",
        api_url=api_url,
        json_body={"decided_by_user_id": user, "decision_note": note},
    )
    emit(payload, json_output=json_output, lines=[_approval_line(payload)])


@validation_app.command("results")
def validation_results(
    task_id: str,
    api_url: ApiUrlOption = DEFAULT_API_URL,
    json_output: JsonOption = False,
) -> None:
    payload = request_json("GET", f"/tasks/{task_id}/validations", api_url=api_url)
    lines = [
        f"{run['id']} {run['status']} exit={run['exit_code']} {run['command']}"
        for run in payload.get("validations", [])
    ]
    emit(payload, json_output=json_output, lines=lines)


def request_json(
    method: str,
    path: str,
    *,
    api_url: str,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = validated_api_url(api_url)
    url = urljoin(f"{base_url}/", path.lstrip("/"))
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.request(method, url, json=json_body)
    except httpx.HTTPError as exc:
        raise typer.BadParameter(f"backend unavailable: {exc}") from exc
    if response.status_code >= HTTP_ERROR_STATUS:
        raise typer.BadParameter(_error_detail(response))
    payload = response.json()
    if not isinstance(payload, dict):
        raise typer.BadParameter("backend returned an unexpected response")
    return payload


def validated_api_url(api_url: str) -> str:
    parsed = urlparse(api_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise typer.BadParameter("api url must be an http(s) URL")
    settings = Settings()
    if settings.local_only and not settings.host_is_local(parsed.hostname):
        raise typer.BadParameter("LOCAL_ONLY blocks non-local API endpoints")
    return api_url.rstrip("/")


def emit(payload: dict[str, Any], *, json_output: bool, lines: list[str]) -> None:
    if json_output:
        typer.echo(redact_secrets(json.dumps(payload, default=str, indent=2)) or "{}")
        return
    for line in lines:
        safe_line = redact_secrets(line)
        if safe_line:
            typer.echo(safe_line)


def _health_lines(payload: dict[str, Any]) -> list[str]:
    return [
        f"status: {payload.get('status', 'unknown')}",
        f"local_only: {payload.get('local_only', 'unknown')}",
        f"environment: {payload.get('environment', 'unknown')}",
    ]


def _repo_line(repository: dict[str, Any]) -> str:
    return f"{repository['id']} {repository['name']} {repository['local_path']}"


def _approval_line(approval: dict[str, Any]) -> str:
    return (
        f"{approval['id']} {approval['status']} "
        f"{approval['requested_action']} risk={approval['risk_level']}"
    )


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"backend returned HTTP {response.status_code}"
    detail = payload.get("detail", payload)
    return redact_secrets(str(detail)) or f"backend returned HTTP {response.status_code}"


if __name__ == "__main__":
    app()
