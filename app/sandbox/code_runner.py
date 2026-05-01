import shlex
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.core.config import Settings, get_settings
from app.sandbox.runner import DockerSandboxRunner, SandboxRejected, SandboxRunner
from app.sandbox.types import SandboxLimits, SandboxRunSpec

CHAT_CODE_COMMAND = ("python", "-B", "/workspace/main.py")
MAX_CODE_CHARS = 20_000
MAX_COMMAND_CHARS = 500
MAX_OUTPUT_CHARS = 12_000


class ChatCodeRunRequest(BaseModel):
    language: str = Field(default="python", pattern="^python$")
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)
    timeout_seconds: int = Field(default=10, ge=1, le=30)


class ChatCodeRunResponse(BaseModel):
    language: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    truncated: bool
    network_enabled: bool


class ChatTerminalRunRequest(BaseModel):
    repository_id: str = Field(min_length=1)
    command: str = Field(min_length=1, max_length=MAX_COMMAND_CHARS)
    timeout_seconds: int = Field(default=10, ge=1, le=60)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        cleaned = value.strip()
        if "\n" in cleaned or "\r" in cleaned:
            raise ValueError("terminal commands must be a single line")
        return cleaned


class ChatTerminalRunResponse(BaseModel):
    repository_id: str
    command: str
    argv: tuple[str, ...]
    category: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    truncated: bool
    network_enabled: bool


class ChatCodeRunner:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runner: SandboxRunner | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.runner = runner or DockerSandboxRunner(engine=self.settings.sandbox_engine)
        self.workspace_root = workspace_root or Path(tempfile.gettempdir()) / "switch-chat-code"

    def run(self, request: ChatCodeRunRequest) -> ChatCodeRunResponse:
        try:
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SandboxRejected(
                f"chat code workspace is unavailable: {self.workspace_root}"
            ) from exc
        with tempfile.TemporaryDirectory(dir=self.workspace_root, prefix="run-") as workspace:
            workspace_path = Path(workspace)
            (workspace_path / "main.py").write_text(request.code, encoding="utf-8")
            result = self.runner.run(
                SandboxRunSpec(
                    command=CHAT_CODE_COMMAND,
                    workspace_path=workspace_path,
                    image=self.settings.sandbox_image,
                    limits=SandboxLimits(
                        cpu_count=self.settings.sandbox_cpu_count,
                        memory=self.settings.sandbox_memory,
                        timeout_seconds=min(
                            request.timeout_seconds,
                            self.settings.sandbox_timeout_seconds,
                        ),
                        disk=self.settings.sandbox_disk,
                    ),
                    network_enabled=False,
                    allow_secret_env=False,
                )
            )
        stdout, stdout_truncated = _truncate(result.stdout)
        stderr, stderr_truncated = _truncate(result.stderr)
        return ChatCodeRunResponse(
            language=request.language,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
            truncated=stdout_truncated or stderr_truncated,
            network_enabled=result.network_enabled,
        )


class ChatTerminalRunner:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runner: SandboxRunner | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.runner = runner or DockerSandboxRunner(engine=self.settings.sandbox_engine)

    def run(
        self, request: ChatTerminalRunRequest, *, workspace_path: Path
    ) -> ChatTerminalRunResponse:
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise SandboxRejected(f"terminal workspace is unavailable: {workspace_path}")
        try:
            command = tuple(shlex.split(request.command))
        except ValueError as exc:
            raise SandboxRejected(f"terminal command could not be parsed: {exc}") from exc
        if not command:
            raise SandboxRejected("terminal command is empty")
        result = self.runner.run(
            SandboxRunSpec(
                command=command,
                workspace_path=workspace_path,
                image=self.settings.sandbox_image,
                limits=SandboxLimits(
                    cpu_count=self.settings.sandbox_cpu_count,
                    memory=self.settings.sandbox_memory,
                    timeout_seconds=min(
                        request.timeout_seconds,
                        self.settings.sandbox_timeout_seconds,
                    ),
                    disk=self.settings.sandbox_disk,
                ),
                network_enabled=False,
                allow_secret_env=False,
            )
        )
        stdout, stdout_truncated = _truncate(result.stdout)
        stderr, stderr_truncated = _truncate(result.stderr)
        return ChatTerminalRunResponse(
            repository_id=request.repository_id,
            command=request.command,
            argv=result.normalized_command,
            category=result.category.value,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
            truncated=stdout_truncated or stderr_truncated,
            network_enabled=result.network_enabled,
        )


def _truncate(value: str) -> tuple[str, bool]:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value, False
    return value[:MAX_OUTPUT_CHARS] + "\n[output truncated]", True
