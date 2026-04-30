from pathlib import Path

from pydantic import BaseModel, Field

from app.patches.types import PatchMetadata


class ToolError(BaseModel):
    code: str
    message: str


class ToolResult(BaseModel):
    success: bool
    error: ToolError | None = None
    artifact_path: str | None = None


class ToolContext(BaseModel):
    agent_run_id: str
    agent_step_id: str
    workspace_path: Path
    actor_user_id: str | None = None


class ReadFileInput(BaseModel):
    path: Path
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=200, ge=1, le=1000)


class ReadFileOutput(ToolResult):
    path: str | None = None
    text: str = ""
    start_line: int = 1
    end_line: int = 0


class ListFilesInput(BaseModel):
    path: Path = Path(".")
    max_files: int = Field(default=200, ge=1, le=2000)


class ListFilesOutput(ToolResult):
    files: list[str] = Field(default_factory=list)


class SearchTextInput(BaseModel):
    query: str = Field(min_length=1)
    max_results: int = Field(default=50, ge=1, le=200)


class SearchTextMatch(BaseModel):
    path: str
    line_number: int
    line: str


class SearchTextOutput(ToolResult):
    matches: list[SearchTextMatch] = Field(default_factory=list)


class SearchSymbolsInput(BaseModel):
    query: str = Field(min_length=1)
    max_results: int = Field(default=50, ge=1, le=200)


class SymbolMatch(BaseModel):
    path: str
    name: str
    kind: str
    start_line: int
    end_line: int


class SearchSymbolsOutput(ToolResult):
    symbols: list[SymbolMatch] = Field(default_factory=list)


class RetrieveContextInput(BaseModel):
    query: str = Field(min_length=1)
    max_bundles: int = Field(default=8, ge=1, le=50)
    max_context_tokens: int = Field(default=1600, ge=1, le=16000)


class ContextBundleOutput(BaseModel):
    path: str
    start_line: int
    end_line: int
    text: str
    reasons: list[str]
    lanes: list[str]
    score: float


class RetrieveContextOutput(ToolResult):
    bundles: list[ContextBundleOutput] = Field(default_factory=list)
    total_estimated_tokens: int = 0


class ProposePatchInput(BaseModel):
    path: Path
    original_text: str
    replacement_text: str
    allow_binary: bool = False
    approval_request_id: str | None = None
    human_approved: bool = False


class ProposePatchOutput(ToolResult):
    path: str | None = None
    diff: str = ""
    patch_artifact_id: str | None = None
    metadata: PatchMetadata | None = None
    approval_required: bool = False


class ApplyPatchInput(BaseModel):
    path: Path
    original_text: str
    replacement_text: str
    branch: str | None = None
    unified_diff: str | None = None
    human_approved: bool = False
    approval_request_id: str | None = None
    allow_binary: bool = False


class ApplyPatchOutput(ToolResult):
    path: str | None = None
    changed: bool = False
    changed_files: list[str] = Field(default_factory=list)
    added_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    rollback_patch: str = ""
    patch_artifact_id: str | None = None
    rollback_artifact_id: str | None = None
    metadata: PatchMetadata | None = None
    approval_required: bool = False


class GetGitDiffInput(BaseModel):
    path: Path | None = None
    max_chars: int = Field(default=12000, ge=100, le=50000)


class GetGitDiffOutput(ToolResult):
    diff: str = ""
    truncated: bool = False


class RunValidationCommandInput(BaseModel):
    command: tuple[str, ...] = Field(min_length=1)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    sandbox_image: str = "python:3.12-slim"
    read_only_workspace: bool = True
    network_enabled: bool = False
    human_approved: bool = False
    approval_request_id: str | None = None
    cpu_count: float = Field(default=1.0, gt=0)
    memory: str = "1g"
    disk: str = "1g"


class RunValidationCommandOutput(ToolResult):
    command: tuple[str, ...] = ()
    normalized_command: tuple[str, ...] = ()
    category: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    validation_run_id: str | None = None
    network_enabled: bool = False


class SummarizeDiffInput(BaseModel):
    diff: str
    max_files: int = Field(default=20, ge=1, le=200)


class DiffFileSummary(BaseModel):
    path: str
    added_lines: int
    removed_lines: int
    status: str = "modified"
    high_risk_categories: list[str] = Field(default_factory=list)


class SummarizeDiffOutput(ToolResult):
    files: list[DiffFileSummary] = Field(default_factory=list)
    total_added: int = 0
    total_removed: int = 0
    human_summary: str = ""
    high_risk_categories: list[str] = Field(default_factory=list)
    approval_required: bool = False


class RequestApprovalInput(BaseModel):
    reason: str = Field(min_length=1)
    requested_action: str = Field(default="unspecified", min_length=1, max_length=120)
    risk_level: str = Field(default="medium", min_length=1, max_length=40)
    diff_summary: str | None = None
    command: str | None = Field(default=None, max_length=240)


class RequestApprovalOutput(ToolResult):
    approval_request_id: str | None = None
    status: str | None = None


class CreateBranchArtifactInput(BaseModel):
    branch_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    human_approved: bool = False
    approval_request_id: str | None = None


class CreateBranchArtifactOutput(ToolResult):
    branch_name: str | None = None
    artifact_path: str | None = None
