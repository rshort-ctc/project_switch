import subprocess
from pathlib import Path

import pytest

from app.sandbox import DockerSandboxRunner, SandboxLimits, SandboxRejected, SandboxRunSpec
from app.sandbox.code_runner import CHAT_CODE_COMMAND, ChatCodeRunner, ChatCodeRunRequest
from app.sandbox.runner import ContainerProcessResult
from app.sandbox.types import SandboxCommandCategory


class CapturingRuntime:
    def __init__(self, result: ContainerProcessResult | None = None, timeout: bool = False) -> None:
        self.result = result or ContainerProcessResult(returncode=0, stdout="ok", stderr="")
        self.timeout = timeout
        self.args: list[str] | None = None
        self.killed: tuple[str, str] | None = None

    def run(self, args: list[str], *, timeout_seconds: int) -> ContainerProcessResult:
        self.args = args
        if self.timeout:
            raise subprocess.TimeoutExpired(args, timeout_seconds, output="partial")
        return self.result

    def kill(self, engine: str, name: str) -> None:
        self.killed = (engine, name)


def test_allowed_command_builds_network_disabled_container_args(tmp_path: Path) -> None:
    runtime = CapturingRuntime()
    runner = DockerSandboxRunner(engine="docker", runtime=runtime)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = runner.run(
        SandboxRunSpec(
            command=("pytest", "-q"),
            workspace_path=workspace,
            limits=SandboxLimits(timeout_seconds=5),
        )
    )

    assert result.exit_code == 0
    assert result.category is SandboxCommandCategory.TESTS
    assert runtime.args is not None
    assert runtime.args[runtime.args.index("--network") + 1] == "none"
    assert runtime.args[runtime.args.index("--cap-drop") + 1] == "ALL"
    assert runtime.args[runtime.args.index("--security-opt") + 1] == "no-new-privileges"
    assert runtime.args[runtime.args.index("--memory-swap") + 1] == "1g"
    assert "--mount" in runtime.args
    assert "PYTHONDONTWRITEBYTECODE=1" in runtime.args
    assert "SECRET_KEY" not in " ".join(runtime.args)


def test_disallowed_command_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = DockerSandboxRunner(engine="docker", runtime=CapturingRuntime())

    with pytest.raises(SandboxRejected, match="allowlist"):
        runner.run(SandboxRunSpec(command=("bash", "-lc", "echo bad"), workspace_path=workspace))


def test_chat_code_command_is_allowed_in_sandbox(tmp_path: Path) -> None:
    runtime = CapturingRuntime(
        result=ContainerProcessResult(returncode=0, stdout="42\n", stderr="")
    )
    runner = DockerSandboxRunner(engine="docker", runtime=runtime)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "main.py").write_text("print(42)", encoding="utf-8")

    result = runner.run(SandboxRunSpec(command=CHAT_CODE_COMMAND, workspace_path=workspace))

    assert result.category is SandboxCommandCategory.CODE
    assert result.stdout == "42\n"
    assert runtime.args is not None
    assert runtime.args[runtime.args.index("--network") + 1] == "none"


def test_chat_code_runner_uses_isolated_workspace(tmp_path: Path) -> None:
    runtime = CapturingRuntime(result=ContainerProcessResult(returncode=0, stdout="ok", stderr=""))
    sandbox = DockerSandboxRunner(engine="docker", runtime=runtime)
    runner = ChatCodeRunner(runner=sandbox, workspace_root=tmp_path)

    result = runner.run(ChatCodeRunRequest(code="print('ok')", timeout_seconds=5))

    assert result.exit_code == 0
    assert result.stdout == "ok"
    assert result.network_enabled is False
    assert runtime.args is not None
    assert "/workspace/main.py" in runtime.args
    assert "SECRET_KEY" not in " ".join(runtime.args)


def test_chat_code_runner_rejects_unavailable_workspace(tmp_path: Path) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("blocked", encoding="utf-8")
    runner = ChatCodeRunner(
        runner=DockerSandboxRunner(engine="docker", runtime=CapturingRuntime()),
        workspace_root=blocking_file / "child",
    )

    with pytest.raises(SandboxRejected, match="workspace is unavailable"):
        runner.run(ChatCodeRunRequest(code="print('ok')"))


def test_timeout_kills_container(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = CapturingRuntime(timeout=True)
    runner = DockerSandboxRunner(engine="docker", runtime=runtime)

    result = runner.run(
        SandboxRunSpec(
            command=("pytest", "-q"),
            workspace_path=workspace,
            limits=SandboxLimits(timeout_seconds=1),
        )
    )

    assert result.timed_out
    assert result.exit_code is None
    assert runtime.killed is not None


def test_network_can_only_be_enabled_explicitly(tmp_path: Path) -> None:
    runtime = CapturingRuntime()
    runner = DockerSandboxRunner(engine="docker", runtime=runtime)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = runner.run(
        SandboxRunSpec(
            command=("ruff", "check", "."),
            workspace_path=workspace,
            network_enabled=True,
        )
    )

    assert result.network_enabled
    assert runtime.args is not None
    assert runtime.args[runtime.args.index("--network") + 1] == "bridge"
