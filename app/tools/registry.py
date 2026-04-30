import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.repositories import ValidationRunRepository
from app.indexing.service import RepoIndexer
from app.models.entities import ApprovalRequest, ValidationRun
from app.models.enums import AgentRunStatus, ApprovalStatus, ValidationStatus
from app.patches import PatchRejected, PatchService
from app.retrieval import RetrievalEngine, RetrievalQuery
from app.sandbox import (
    DockerSandboxRunner,
    SandboxLimits,
    SandboxRejected,
    SandboxRunner,
    SandboxRunSpec,
)
from app.security import PolicyEngine, PolicyOperation, PolicyRequest
from app.services.runs import RunService
from app.tools.runtime import ToolRuntime, compact_text
from app.tools.schemas import (
    ApplyPatchInput,
    ApplyPatchOutput,
    ContextBundleOutput,
    CreateBranchArtifactInput,
    CreateBranchArtifactOutput,
    DiffFileSummary,
    GetGitDiffInput,
    GetGitDiffOutput,
    ListFilesInput,
    ListFilesOutput,
    ProposePatchInput,
    ProposePatchOutput,
    ReadFileInput,
    ReadFileOutput,
    RequestApprovalInput,
    RequestApprovalOutput,
    RetrieveContextInput,
    RetrieveContextOutput,
    RunValidationCommandInput,
    RunValidationCommandOutput,
    SearchSymbolsInput,
    SearchSymbolsOutput,
    SearchTextInput,
    SearchTextMatch,
    SearchTextOutput,
    SummarizeDiffInput,
    SummarizeDiffOutput,
    SymbolMatch,
    ToolContext,
    ToolError,
)


class ToolRegistry:
    def __init__(
        self,
        *,
        session: Session,
        policy: PolicyEngine,
        context: ToolContext,
        indexer: RepoIndexer | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        sandbox_runner: SandboxRunner | None = None,
    ) -> None:
        self.session = session
        self.policy = policy
        self.context = context
        self.runtime = ToolRuntime(session=session, policy=policy, context=context)
        self.indexer = indexer
        self.retrieval_engine = retrieval_engine
        settings = get_settings()
        self.sandbox_runner = sandbox_runner or DockerSandboxRunner(engine=settings.sandbox_engine)

    def read_file(self, input_model: ReadFileInput) -> ReadFileOutput:
        return self.runtime.run(
            tool_name="read_file",
            input_model=input_model,
            output_factory=lambda error: ReadFileOutput(success=False, error=error),
            action=lambda: self._read_file(input_model),
        )

    def list_files(self, input_model: ListFilesInput) -> ListFilesOutput:
        return self.runtime.run(
            tool_name="list_files",
            input_model=input_model,
            output_factory=lambda error: ListFilesOutput(success=False, error=error),
            action=lambda: self._list_files(input_model),
        )

    def search_text(self, input_model: SearchTextInput) -> SearchTextOutput:
        return self.runtime.run(
            tool_name="search_text",
            input_model=input_model,
            output_factory=lambda error: SearchTextOutput(success=False, error=error),
            action=lambda: self._search_text(input_model),
        )

    def search_symbols(self, input_model: SearchSymbolsInput) -> SearchSymbolsOutput:
        return self.runtime.run(
            tool_name="search_symbols",
            input_model=input_model,
            output_factory=lambda error: SearchSymbolsOutput(success=False, error=error),
            action=lambda: self._search_symbols(input_model),
        )

    def retrieve_context(self, input_model: RetrieveContextInput) -> RetrieveContextOutput:
        return self.runtime.run(
            tool_name="retrieve_context",
            input_model=input_model,
            output_factory=lambda error: RetrieveContextOutput(success=False, error=error),
            action=lambda: self._retrieve_context(input_model),
        )

    def propose_patch(self, input_model: ProposePatchInput) -> ProposePatchOutput:
        return self.runtime.run(
            tool_name="propose_patch",
            input_model=input_model,
            output_factory=lambda error: ProposePatchOutput(success=False, error=error),
            action=lambda: self._propose_patch(input_model),
        )

    def apply_patch_to_workspace(self, input_model: ApplyPatchInput) -> ApplyPatchOutput:
        return self.runtime.run(
            tool_name="apply_patch_to_workspace",
            input_model=input_model,
            output_factory=lambda error: ApplyPatchOutput(success=False, error=error),
            action=lambda: self._apply_patch(input_model),
        )

    def get_git_diff(self, input_model: GetGitDiffInput) -> GetGitDiffOutput:
        return self.runtime.run(
            tool_name="get_git_diff",
            input_model=input_model,
            output_factory=lambda error: GetGitDiffOutput(success=False, error=error),
            action=lambda: self._get_git_diff(input_model),
        )

    def run_validation_command(
        self, input_model: RunValidationCommandInput
    ) -> RunValidationCommandOutput:
        return self.runtime.run(
            tool_name="run_validation_command",
            input_model=input_model,
            output_factory=lambda error: RunValidationCommandOutput(success=False, error=error),
            action=lambda: self._run_validation_command(input_model),
        )

    def summarize_diff(self, input_model: SummarizeDiffInput) -> SummarizeDiffOutput:
        return self.runtime.run(
            tool_name="summarize_diff",
            input_model=input_model,
            output_factory=lambda error: SummarizeDiffOutput(success=False, error=error),
            action=lambda: self._summarize_diff(input_model),
        )

    def request_approval(self, input_model: RequestApprovalInput) -> RequestApprovalOutput:
        return self.runtime.run(
            tool_name="request_approval",
            input_model=input_model,
            output_factory=lambda error: RequestApprovalOutput(success=False, error=error),
            action=lambda: self._request_approval(input_model),
            approval_required=True,
        )

    def create_branch_artifact(
        self, input_model: CreateBranchArtifactInput
    ) -> CreateBranchArtifactOutput:
        return self.runtime.run(
            tool_name="create_branch_artifact",
            input_model=input_model,
            output_factory=lambda error: CreateBranchArtifactOutput(success=False, error=error),
            action=lambda: self._create_branch_artifact(input_model),
            approval_required=True,
        )

    def _read_file(self, input_model: ReadFileInput) -> ReadFileOutput:
        self.policy.assert_allowed(
            PolicyRequest(operation=PolicyOperation.READ_PATH, path=input_model.path)
        )
        path = self._resolve(input_model.path)
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        start_index = input_model.start_line - 1
        selected = lines[start_index : start_index + input_model.max_lines]
        text, truncated = compact_text("\n".join(selected))
        artifact = self._write_artifact_if_truncated(
            "read_file.txt", "\n".join(selected), truncated
        )
        return ReadFileOutput(
            success=True,
            path=input_model.path.as_posix(),
            text=text,
            start_line=input_model.start_line,
            end_line=input_model.start_line + len(selected) - 1,
            artifact_path=artifact,
        )

    def _list_files(self, input_model: ListFilesInput) -> ListFilesOutput:
        self.policy.assert_allowed(
            PolicyRequest(operation=PolicyOperation.READ_PATH, path=input_model.path)
        )
        root = self._resolve(input_model.path)
        files: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file() or ".git" in path.parts or ".switch" in path.parts:
                continue
            relative = path.relative_to(self.context.workspace_path)
            evaluation = self.policy.evaluate(
                PolicyRequest(operation=PolicyOperation.READ_PATH, path=relative)
            )
            if evaluation.allowed:
                files.append(relative.as_posix())
        return ListFilesOutput(success=True, files=sorted(files)[: input_model.max_files])

    def _search_text(self, input_model: SearchTextInput) -> SearchTextOutput:
        matches: list[SearchTextMatch] = []
        for path in self.context.workspace_path.rglob("*"):
            if not path.is_file() or ".git" in path.parts or ".switch" in path.parts:
                continue
            relative = path.relative_to(self.context.workspace_path)
            evaluation = self.policy.evaluate(
                PolicyRequest(operation=PolicyOperation.READ_PATH, path=relative)
            )
            if not evaluation.allowed:
                continue
            for index, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
            ):
                if input_model.query in line:
                    matches.append(
                        SearchTextMatch(
                            path=relative.as_posix(),
                            line_number=index,
                            line=line[:500],
                        )
                    )
                    if len(matches) >= input_model.max_results:
                        return SearchTextOutput(success=True, matches=matches)
        return SearchTextOutput(success=True, matches=matches)

    def _search_symbols(self, input_model: SearchSymbolsInput) -> SearchSymbolsOutput:
        if self.indexer is None:
            return SearchSymbolsOutput(
                success=False,
                error=ToolError(code="index_unavailable", message="symbol index is unavailable"),
            )
        symbols = self.indexer.search_symbols(input_model.query)[: input_model.max_results]
        return SearchSymbolsOutput(
            success=True,
            symbols=[
                SymbolMatch(
                    path=symbol.file_path,
                    name=symbol.name,
                    kind=symbol.kind.value,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                )
                for symbol in symbols
            ],
        )

    def _retrieve_context(self, input_model: RetrieveContextInput) -> RetrieveContextOutput:
        if self.retrieval_engine is None:
            return RetrieveContextOutput(
                success=False,
                error=ToolError(
                    code="retrieval_unavailable", message="retrieval engine is unavailable"
                ),
            )
        result = self.retrieval_engine.retrieve(
            RetrievalQuery(
                task=input_model.query,
                max_bundles=input_model.max_bundles,
                max_context_tokens=input_model.max_context_tokens,
            )
        )
        return RetrieveContextOutput(
            success=True,
            bundles=[
                ContextBundleOutput(
                    path=bundle.citation.file_path,
                    start_line=bundle.citation.start_line,
                    end_line=bundle.citation.end_line,
                    text=bundle.text,
                    reasons=list(bundle.reasons),
                    lanes=[lane.value for lane in bundle.lanes],
                    score=bundle.score,
                )
                for bundle in result.bundles
            ],
            total_estimated_tokens=result.total_estimated_tokens,
        )

    def _propose_patch(self, input_model: ProposePatchInput) -> ProposePatchOutput:
        self.policy.assert_allowed(
            PolicyRequest(operation=PolicyOperation.PROPOSE_PATCH, path=input_model.path)
        )
        patch_service = self._patch_service()
        diff = patch_service.generate_unified_diff(
            input_model.path, input_model.original_text, input_model.replacement_text
        )
        try:
            metadata = patch_service.analyze_diff(diff, allow_binary=input_model.allow_binary)
        except PatchRejected as exc:
            return ProposePatchOutput(
                success=False,
                error=ToolError(code="patch_rejected", message=str(exc)),
                path=input_model.path.as_posix(),
            )
        artifact_id, artifact_path = patch_service.store_patch_artifact(
            diff=diff,
            metadata=metadata,
        )
        if metadata.approval_required and not self._approval_granted(
            input_model.approval_request_id,
            requested_action="export_patch",
        ):
            self._request_tool_approval(
                requested_action="export_patch",
                risk_level="high",
                reason="High-risk patch export requires human approval",
                diff_summary=metadata.human_summary,
            )
            return ProposePatchOutput(
                success=False,
                error=ToolError(
                    code="approval_required",
                    message="approval required before exporting high-risk patch",
                ),
                path=input_model.path.as_posix(),
                patch_artifact_id=artifact_id,
                artifact_path=artifact_path,
                metadata=metadata,
                approval_required=True,
            )
        compact, truncated = compact_text(diff)
        artifact = (
            self._write_artifact_if_truncated("proposed.patch", diff, truncated)
            if truncated
            else artifact_path
        )
        return ProposePatchOutput(
            success=True,
            path=input_model.path.as_posix(),
            diff=compact,
            artifact_path=artifact,
            patch_artifact_id=artifact_id,
            metadata=metadata,
            approval_required=metadata.approval_required,
        )

    def _apply_patch(self, input_model: ApplyPatchInput) -> ApplyPatchOutput:
        patch_service = self._patch_service()
        diff = input_model.unified_diff
        if diff is None:
            path = self._resolve(input_model.path)
            current = path.read_text(encoding="utf-8", errors="ignore")
            if input_model.original_text not in current:
                return ApplyPatchOutput(
                    success=False,
                    error=ToolError(code="patch_mismatch", message="original text was not found"),
                    path=input_model.path.as_posix(),
                )
            replacement = current.replace(
                input_model.original_text,
                input_model.replacement_text,
                1,
            )
            diff = patch_service.generate_unified_diff(input_model.path, current, replacement)
        try:
            metadata = patch_service.analyze_diff(diff, allow_binary=input_model.allow_binary)
        except PatchRejected as exc:
            return ApplyPatchOutput(
                success=False,
                error=ToolError(code="patch_rejected", message=str(exc)),
                path=input_model.path.as_posix(),
            )
        for changed_path in metadata.changed_files:
            self.policy.assert_allowed(
                PolicyRequest(
                    operation=PolicyOperation.WRITE_FILE,
                    path=Path(changed_path),
                    branch=input_model.branch,
                    content_summary=f"patch file {changed_path}",
                )
            )
        if not self._approval_granted(
            input_model.approval_request_id,
            requested_action="apply_patch",
        ):
            self._request_tool_approval(
                requested_action="apply_patch",
                risk_level="high" if metadata.approval_required else "medium",
                reason="Applying a patch mutates the workspace and requires human approval",
                diff_summary=metadata.human_summary,
            )
            return ApplyPatchOutput(
                success=False,
                error=ToolError(
                    code="approval_required",
                    message="approval required before applying patch to workspace",
                ),
                path=input_model.path.as_posix(),
                metadata=metadata,
                approval_required=True,
            )
        try:
            result = patch_service.apply_patch(
                diff=diff,
                human_approved=True,
                allow_binary=input_model.allow_binary,
            )
        except PatchRejected as exc:
            return ApplyPatchOutput(
                success=False,
                error=ToolError(
                    code="approval_required" if metadata.approval_required else "patch_rejected",
                    message=str(exc),
                ),
                path=input_model.path.as_posix(),
                metadata=metadata,
                approval_required=metadata.approval_required,
            )
        return ApplyPatchOutput(
            success=True,
            path=input_model.path.as_posix(),
            changed=result.applied,
            changed_files=result.metadata.changed_files,
            added_files=result.metadata.added_files,
            deleted_files=result.metadata.deleted_files,
            rollback_patch=result.rollback_patch,
            patch_artifact_id=result.patch_artifact_id,
            rollback_artifact_id=result.rollback_artifact_id,
            metadata=result.metadata,
            approval_required=result.metadata.approval_required,
        )

    def _get_git_diff(self, input_model: GetGitDiffInput) -> GetGitDiffOutput:
        if input_model.path is not None:
            self.policy.assert_allowed(
                PolicyRequest(operation=PolicyOperation.READ_PATH, path=input_model.path)
            )
        command = ["git", "-C", str(self.context.workspace_path), "diff", "--"]
        if input_model.path is not None:
            command.append(input_model.path.as_posix())
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        diff, truncated = compact_text(result.stdout, max_chars=input_model.max_chars)
        artifact = self._write_artifact_if_truncated("git.diff", result.stdout, truncated)
        return GetGitDiffOutput(
            success=result.returncode == 0,
            diff=diff,
            truncated=truncated,
            artifact_path=artifact,
            error=None
            if result.returncode == 0
            else ToolError(code="git_diff_failed", message=result.stderr.strip()),
        )

    def _run_validation_command(
        self, input_model: RunValidationCommandInput
    ) -> RunValidationCommandOutput:
        self.policy.assert_allowed(
            PolicyRequest(
                operation=PolicyOperation.RUN_COMMAND,
                command=input_model.command,
                requires_sandbox=True,
                agent_run_id=self.context.agent_run_id,
            )
        )
        if not self._approval_granted(
            input_model.approval_request_id,
            requested_action="run_validation",
        ):
            self._request_tool_approval(
                requested_action="run_validation",
                risk_level="medium",
                reason="Running validation commands requires human approval",
                command=" ".join(input_model.command),
            )
            return RunValidationCommandOutput(
                success=False,
                error=ToolError(
                    code="approval_required",
                    message="approval required before running validation command",
                ),
                command=input_model.command,
            )
        spec = SandboxRunSpec(
            command=input_model.command,
            workspace_path=self.context.workspace_path,
            image=input_model.sandbox_image,
            limits=SandboxLimits(
                cpu_count=input_model.cpu_count,
                memory=input_model.memory,
                timeout_seconds=input_model.timeout_seconds,
                disk=input_model.disk,
            ),
            read_only_workspace=input_model.read_only_workspace,
            network_enabled=input_model.network_enabled,
        )
        try:
            result = self.sandbox_runner.run(spec)
        except SandboxRejected as exc:
            validation = self._record_validation_run(
                command=input_model.command,
                status=ValidationStatus.FAILED,
                exit_code=None,
                duration_ms=0,
                output_summary=str(exc),
            )
            return RunValidationCommandOutput(
                success=False,
                error=ToolError(code="sandbox_rejected", message=str(exc)),
                command=input_model.command,
                validation_run_id=validation.id,
            )
        stdout, stdout_truncated = compact_text(result.stdout)
        stderr, stderr_truncated = compact_text(result.stderr)
        artifact = None
        if stdout_truncated or stderr_truncated:
            artifact = self.runtime.artifact_path("validation-output.txt")
            artifact.write_text(
                f"STDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}",
                encoding="utf-8",
            )
        status = ValidationStatus.PASSED if result.exit_code == 0 else ValidationStatus.FAILED
        if result.timed_out:
            status = ValidationStatus.CANCELLED
        output_summary = _validation_output_summary(
            stdout=stdout,
            stderr=stderr,
            artifact_path=artifact.relative_to(self.context.workspace_path).as_posix()
            if artifact
            else None,
        )
        validation = self._record_validation_run(
            command=result.normalized_command,
            status=status,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            output_summary=output_summary,
        )
        return RunValidationCommandOutput(
            success=result.exit_code == 0,
            command=input_model.command,
            normalized_command=result.normalized_command,
            category=result.category.value,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
            validation_run_id=validation.id,
            network_enabled=result.network_enabled,
            artifact_path=artifact.relative_to(self.context.workspace_path).as_posix()
            if artifact
            else None,
            error=None
            if result.exit_code == 0
            else ToolError(
                code="validation_timeout" if result.timed_out else "validation_failed",
                message="timeout" if result.timed_out else f"exit code {result.exit_code}",
            ),
        )

    def _summarize_diff(self, input_model: SummarizeDiffInput) -> SummarizeDiffOutput:
        try:
            metadata = self._patch_service().analyze_diff(input_model.diff)
        except PatchRejected as exc:
            return SummarizeDiffOutput(
                success=False,
                error=ToolError(code="patch_rejected", message=str(exc)),
            )
        files = [
            DiffFileSummary(
                path=file.path,
                added_lines=file.added_lines,
                removed_lines=file.deleted_lines,
                status=file.status.value,
                high_risk_categories=[category.value for category in file.high_risk_categories],
            )
            for file in metadata.files[: input_model.max_files]
        ]
        return SummarizeDiffOutput(
            success=True,
            files=files,
            total_added=metadata.total_added_lines,
            total_removed=metadata.total_deleted_lines,
            human_summary=metadata.human_summary,
            high_risk_categories=[category.value for category in metadata.high_risk_categories],
            approval_required=metadata.approval_required,
        )

    def _request_approval(self, input_model: RequestApprovalInput) -> RequestApprovalOutput:
        if self.context.actor_user_id is None:
            return RequestApprovalOutput(
                success=False,
                error=ToolError(
                    code="actor_required",
                    message="approval requests require an actor user id",
                ),
            )
        service = RunService(self.session)
        run = service.runs.get(self.context.agent_run_id)
        if run is not None and AgentRunStatus(run.status) is AgentRunStatus.PENDING:
            service.transition_run(
                agent_run_id=self.context.agent_run_id, status=AgentRunStatus.RUNNING
            )
        approval = service.request_approval(
            agent_run_id=self.context.agent_run_id,
            requested_by_user_id=self.context.actor_user_id,
            reason=input_model.reason,
            requested_action=input_model.requested_action,
            risk_level=input_model.risk_level,
            diff_summary=input_model.diff_summary,
            command=input_model.command,
        )
        return RequestApprovalOutput(
            success=True,
            approval_request_id=approval.id,
            status=str(approval.status),
        )

    def _create_branch_artifact(
        self, input_model: CreateBranchArtifactInput
    ) -> CreateBranchArtifactOutput:
        if not self._approval_granted(
            input_model.approval_request_id,
            requested_action="create_branch_artifact",
        ):
            self._request_tool_approval(
                requested_action="create_branch_artifact",
                risk_level="high",
                reason="Branch or PR artifacts require human approval",
                diff_summary=input_model.summary,
            )
            return CreateBranchArtifactOutput(
                success=False,
                error=ToolError(
                    code="approval_required",
                    message="approval required before creating branch artifact",
                ),
            )
        self.policy.assert_allowed(
            PolicyRequest(
                operation=PolicyOperation.CREATE_BRANCH_ARTIFACT,
                branch=input_model.branch_name,
                human_approved=True,
            )
        )
        artifact = self.runtime.artifact_path(
            f"branch-{input_model.branch_name.replace('/', '-')}.txt"
        )
        artifact.write_text(
            f"branch={input_model.branch_name}\nsummary={input_model.summary}\n",
            encoding="utf-8",
        )
        return CreateBranchArtifactOutput(
            success=True,
            branch_name=input_model.branch_name,
            artifact_path=artifact.relative_to(self.context.workspace_path).as_posix(),
        )

    def _request_tool_approval(
        self,
        *,
        requested_action: str,
        risk_level: str,
        reason: str,
        diff_summary: str | None = None,
        command: str | None = None,
    ) -> ApprovalRequest | None:
        if self.context.actor_user_id is None:
            return None
        return RunService(self.session).request_approval(
            agent_run_id=self.context.agent_run_id,
            requested_by_user_id=self.context.actor_user_id,
            requested_action=requested_action,
            risk_level=risk_level,
            reason=reason,
            diff_summary=diff_summary,
            command=command,
        )

    def _approval_granted(
        self,
        approval_request_id: str | None,
        *,
        requested_action: str,
    ) -> bool:
        if approval_request_id is None:
            return False
        approval = self.session.get(ApprovalRequest, approval_request_id)
        return (
            approval is not None
            and approval.agent_run_id == self.context.agent_run_id
            and approval.requested_action == requested_action
            and ApprovalStatus(approval.status) is ApprovalStatus.APPROVED
        )

    def _resolve(self, path: Path) -> Path:
        resolved = (
            (self.context.workspace_path / path).resolve()
            if not path.is_absolute()
            else path.resolve()
        )
        return resolved

    def _write_artifact_if_truncated(self, name: str, value: str, truncated: bool) -> str | None:
        if not truncated:
            return None
        artifact = self.runtime.artifact_path(name)
        artifact.write_text(value, encoding="utf-8")
        return artifact.relative_to(self.context.workspace_path).as_posix()

    def _patch_service(self) -> PatchService:
        return PatchService(
            session=self.session,
            workspace_path=self.context.workspace_path,
            agent_run_id=self.context.agent_run_id,
            actor_user_id=self.context.actor_user_id,
        )

    def _record_validation_run(
        self,
        *,
        command: tuple[str, ...],
        status: ValidationStatus,
        exit_code: int | None,
        duration_ms: int,
        output_summary: str | None,
    ) -> ValidationRun:
        return ValidationRunRepository(self.session).create(
            agent_run_id=self.context.agent_run_id,
            command=" ".join(command)[:240],
            duration_ms=duration_ms,
            status=status,
            exit_code=exit_code,
            output_summary=output_summary,
        )


def _validation_output_summary(
    *,
    stdout: str,
    stderr: str,
    artifact_path: str | None,
) -> str:
    parts = []
    if stdout:
        parts.append(f"stdout={stdout[:500]}")
    if stderr:
        parts.append(f"stderr={stderr[:500]}")
    if artifact_path is not None:
        parts.append(f"artifact={artifact_path}")
    return "\n".join(parts)[:2000]
