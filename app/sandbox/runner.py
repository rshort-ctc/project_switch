import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.sandbox.types import SandboxCommandCategory, SandboxResult, SandboxRunSpec

MIN_PYTHON_MODULE_COMMAND_PARTS = 3
MIN_PYTHON_B_FLAG_MODULE_COMMAND_PARTS = 4


class SandboxRejected(ValueError):
    pass


@dataclass(frozen=True)
class ContainerProcessResult:
    returncode: int
    stdout: str
    stderr: str


class ContainerRuntime(Protocol):
    def run(self, args: list[str], *, timeout_seconds: int) -> ContainerProcessResult:
        """Run the container engine command."""

    def kill(self, engine: str, name: str) -> None:
        """Force-remove a timed-out container by name."""


class SandboxRunner(Protocol):
    def run(self, spec: SandboxRunSpec) -> SandboxResult:
        """Run a validation command in an isolated sandbox."""


class SubprocessContainerRuntime:
    def run(self, args: list[str], *, timeout_seconds: int) -> ContainerProcessResult:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return ContainerProcessResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def kill(self, engine: str, name: str) -> None:
        subprocess.run(
            [engine, "rm", "-f", name],
            check=False,
            capture_output=True,
            text=True,
        )


class DockerSandboxRunner:
    def __init__(
        self,
        *,
        engine: str = "auto",
        runtime: ContainerRuntime | None = None,
    ) -> None:
        self.engine = engine
        self._runtime_supplied = runtime is not None
        self.runtime = runtime or SubprocessContainerRuntime()

    def run(self, spec: SandboxRunSpec) -> SandboxResult:
        category, normalized = classify_command(spec.command)
        engine = self._resolve_engine()
        name = f"switch-sandbox-{uuid4().hex}"
        args = self._container_args(
            engine=engine,
            name=name,
            spec=spec,
            normalized_command=normalized,
        )
        started = time.monotonic()
        try:
            process = self.runtime.run(args, timeout_seconds=spec.limits.timeout_seconds)
            timed_out = False
            exit_code: int | None = process.returncode
            stdout = process.stdout
            stderr = process.stderr
        except subprocess.TimeoutExpired as exc:
            self.runtime.kill(engine, name)
            timed_out = True
            exit_code = None
            stdout = _decode_timeout_output(exc.stdout)
            stderr = _decode_timeout_output(exc.stderr) or "sandbox command timed out"
        duration_ms = int((time.monotonic() - started) * 1000)
        return SandboxResult(
            command=spec.command,
            normalized_command=normalized,
            category=category,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            network_enabled=spec.network_enabled,
        )

    def _resolve_engine(self) -> str:
        if self.engine in {"docker", "podman"}:
            if self._runtime_supplied:
                return self.engine
            if shutil.which(self.engine) is None:
                raise SandboxRejected(f"container engine is unavailable: {self.engine}")
            return self.engine
        for engine in ("podman", "docker"):
            if shutil.which(engine) is not None:
                return engine
        raise SandboxRejected("neither podman nor docker is available")

    def _container_args(
        self,
        *,
        engine: str,
        name: str,
        spec: SandboxRunSpec,
        normalized_command: tuple[str, ...],
    ) -> list[str]:
        workspace = spec.workspace_path.resolve()
        if not workspace.exists():
            raise SandboxRejected(f"workspace does not exist: {workspace}")
        mount = f"type=bind,source={workspace},target=/workspace"
        if spec.read_only_workspace:
            mount = f"{mount},readonly"
        network = "bridge" if spec.network_enabled else "none"
        args = [
            engine,
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            network,
            "--cpus",
            str(spec.limits.cpu_count),
            "--memory",
            spec.limits.memory,
            "--pids-limit",
            "256",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory-swap",
            spec.limits.memory,
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={spec.limits.disk}",
            "--mount",
            mount,
            "--workdir",
            "/workspace",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            spec.image,
            *normalized_command,
        ]
        return args


def classify_command(command: tuple[str, ...]) -> tuple[SandboxCommandCategory, tuple[str, ...]]:
    normalized = _normalize_command(command)
    category = _category_for(normalized)
    if category is None:
        raise SandboxRejected(f"command is not in the sandbox allowlist: {' '.join(command)}")
    return category, normalized


def _normalize_command(command: tuple[str, ...]) -> tuple[str, ...]:
    if (
        len(command) >= MIN_PYTHON_MODULE_COMMAND_PARTS
        and Path(command[0]).name.startswith("python")
        and command[1] in {"-m", "-B"}
    ):
        if command[1] == "-m":
            return ("python", "-m", *command[2:])
        if len(command) >= MIN_PYTHON_B_FLAG_MODULE_COMMAND_PARTS and command[2] == "-m":
            return ("python", "-B", "-m", *command[3:])
    return command


def _category_for(command: tuple[str, ...]) -> SandboxCommandCategory | None:  # noqa: PLR0911
    if command == ("python", "-B", "/workspace/main.py"):
        return SandboxCommandCategory.CODE
    if command[:1] == ("pytest",):
        return SandboxCommandCategory.TESTS
    if command[:3] in {("python", "-m", "pytest"), ("python", "-B", "-m")} and "pytest" in command:
        return SandboxCommandCategory.TESTS
    if command[:2] == ("ruff", "check"):
        return SandboxCommandCategory.LINT
    if command[:2] == ("ruff", "format") and "--check" in command:
        return SandboxCommandCategory.FORMAT_CHECK
    if command[:1] == ("mypy",):
        return SandboxCommandCategory.TYPECHECK
    if command[:1] in {("npm",), ("pnpm",), ("yarn",)} and "build" in command:
        return SandboxCommandCategory.BUILD
    if command[:2] == ("python", "-m") and len(command) >= MIN_PYTHON_MODULE_COMMAND_PARTS:
        module = command[2]
        if module == "mypy":
            return SandboxCommandCategory.TYPECHECK
        if module == "build":
            return SandboxCommandCategory.BUILD
    return None


def _decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value
