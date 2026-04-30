from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class SandboxCommandCategory(StrEnum):
    TESTS = "tests"
    LINT = "lint"
    TYPECHECK = "typecheck"
    BUILD = "build"
    FORMAT_CHECK = "format_check"


class SandboxLimits(BaseModel):
    cpu_count: float = Field(default=1.0, gt=0)
    memory: str = "1g"
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    disk: str = "1g"


class SandboxRunSpec(BaseModel):
    command: tuple[str, ...] = Field(min_length=1)
    workspace_path: Path
    image: str = "python:3.12-slim"
    limits: SandboxLimits = Field(default_factory=SandboxLimits)
    read_only_workspace: bool = False
    network_enabled: bool = False
    allow_secret_env: bool = False


class SandboxResult(BaseModel):
    command: tuple[str, ...]
    normalized_command: tuple[str, ...]
    category: SandboxCommandCategory
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    network_enabled: bool = False
    artifact_path: str | None = None
