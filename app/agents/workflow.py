import time
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.indexing.service import RepoIndexer
from app.models.entities import AgentStep
from app.models.enums import AgentRunStatus, AgentStepStatus
from app.retrieval import RetrievalEngine
from app.sandbox import SandboxRunner
from app.security import PermissionLevel, PolicyEngine
from app.services.audit import AuditService
from app.services.runs import RunService
from app.tools import ToolContext, ToolRegistry
from app.tools.schemas import (
    ApplyPatchInput,
    ApplyPatchOutput,
    ContextBundleOutput,
    GetGitDiffInput,
    ProposePatchInput,
    ProposePatchOutput,
    RequestApprovalInput,
    RetrieveContextInput,
    RunValidationCommandInput,
    SummarizeDiffInput,
)


class WorkflowState(StrEnum):
    INTAKE = "intake"
    CLASSIFY_TASK = "classify_task"
    RETRIEVE_CONTEXT = "retrieve_context"
    DRAFT_PLAN = "draft_plan"
    RISK_ASSESSMENT = "risk_assessment"
    APPROVAL_IF_NEEDED = "approval_if_needed"
    GENERATE_PATCH = "generate_patch"
    APPLY_PATCH_WORKSPACE = "apply_patch_workspace"
    RUN_VALIDATION = "run_validation"
    ANALYZE_FAILURES = "analyze_failures"
    REVISE_PATCH_LIMITED = "revise_patch_limited"
    REVIEW_DIFF = "review_diff"
    FINAL_REPORT = "final_report"


class WorkflowStatus(StrEnum):
    COMPLETED = "completed"
    WAITING_APPROVAL = "waiting_approval"
    FAILED = "failed"
    STOPPED = "stopped"


class WorkflowStopReason(StrEnum):
    APPROVAL_REQUIRED = "approval_required"
    CONTEXT_CONFIDENCE_LOW = "context_confidence_low"
    POLICY_BLOCKED = "policy_blocked"
    PATCH_MISMATCH = "patch_mismatch"
    VALIDATION_FAILED = "validation_failed"
    REPEATED_FAILURE = "repeated_failure"
    MAX_PATCH_ATTEMPTS = "max_patch_attempts"


class WorkflowModel(Protocol):
    def complete(
        self,
        *,
        state: WorkflowState,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Return a structured model response for the given deterministic state."""


class WorkflowConfig(BaseModel):
    max_patch_attempts: int = Field(default=3, ge=1, le=3)
    context_min_score: float = Field(default=0.1, ge=0.0)
    retrieval_max_bundles: int = Field(default=8, ge=1, le=50)
    retrieval_max_context_tokens: int = Field(default=1600, ge=1, le=16000)
    validation_command: tuple[str, ...] | None = ("pytest",)
    validation_timeout_seconds: int = Field(default=60, ge=1, le=600)


class WorkflowInput(BaseModel):
    task: str = Field(min_length=1)
    validation_command: tuple[str, ...] | None = None
    base_branch: str | None = None


class PatchInstruction(BaseModel):
    path: Path
    original_text: str
    replacement_text: str


class WorkflowCitation(BaseModel):
    path: str
    start_line: int
    end_line: int
    reasons: list[str] = Field(default_factory=list)


class WorkflowFinalReport(BaseModel):
    status: WorkflowStatus
    task: str
    summary: str
    stop_reason: WorkflowStopReason | None = None
    approval_required: bool = False
    policy_blocked: bool = False
    files_cited: list[WorkflowCitation] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    patch_attempts: int = 0
    tests_ran: bool = False
    tests_passed: bool | None = None
    validation_command: tuple[str, ...] | None = None
    validation_exit_code: int | None = None
    notes: list[str] = Field(default_factory=list)


class WorkflowResult(BaseModel):
    status: WorkflowStatus
    states: list[WorkflowState]
    patch_attempts: int
    validation_runs: int
    final_report: WorkflowFinalReport


T = TypeVar("T")
FAILURE_SIGNATURE_CHARS = 1000


class DeterministicCodingAgentWorkflow:
    def __init__(
        self,
        *,
        session: Session,
        model: WorkflowModel,
        policy: PolicyEngine,
        workspace_path: Path,
        agent_run_id: str,
        actor_user_id: str | None = None,
        indexer: RepoIndexer | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        sandbox_runner: SandboxRunner | None = None,
        config: WorkflowConfig | None = None,
    ) -> None:
        self.session = session
        self.model = model
        self.policy = policy
        self.workspace_path = workspace_path
        self.agent_run_id = agent_run_id
        self.actor_user_id = actor_user_id
        self.indexer = indexer
        self.retrieval_engine = retrieval_engine
        self.sandbox_runner = sandbox_runner
        self.config = config or WorkflowConfig()
        self.runs = RunService(session)
        self.audit = AuditService(session)
        self._sequence = 0
        self._states: list[WorkflowState] = []

    def run(self, input_model: WorkflowInput) -> WorkflowResult:  # noqa: PLR0912, PLR0915
        self._ensure_run_running()
        context_bundles: list[ContextBundleOutput] = []
        changed_files: set[str] = set()
        notes: list[str] = []
        patch_attempts = 0
        validation_runs = 0
        tests_ran = False
        tests_passed: bool | None = None
        validation_exit_code: int | None = None
        failure_signatures: set[str] = set()
        last_failure_signature: str | None = None
        policy_blocked = False
        approval_required = False
        status = WorkflowStatus.STOPPED
        stop_reason: WorkflowStopReason | None = None

        self._run_step(WorkflowState.INTAKE, lambda step: "task accepted")

        classification = self._run_step(
            WorkflowState.CLASSIFY_TASK,
            lambda step: self._model_call(
                WorkflowState.CLASSIFY_TASK,
                {"task": input_model.task},
            ),
        )

        context_output = self._run_step(
            WorkflowState.RETRIEVE_CONTEXT,
            lambda step: self._tools(step).retrieve_context(
                RetrieveContextInput(
                    query=input_model.task,
                    max_bundles=self.config.retrieval_max_bundles,
                    max_context_tokens=self.config.retrieval_max_context_tokens,
                )
            ),
        )
        if context_output.success:
            context_bundles = context_output.bundles
        else:
            notes.append(_tool_error_message(context_output.error))

        if not self._context_confident(context_bundles):
            status = WorkflowStatus.STOPPED
            stop_reason = WorkflowStopReason.CONTEXT_CONFIDENCE_LOW
            notes.append("retrieval confidence was too low to continue")
            return self._finish(
                input_model=input_model,
                status=status,
                stop_reason=stop_reason,
                approval_required=approval_required,
                policy_blocked=policy_blocked,
                context_bundles=context_bundles,
                changed_files=sorted(changed_files),
                patch_attempts=patch_attempts,
                validation_runs=validation_runs,
                tests_ran=tests_ran,
                tests_passed=tests_passed,
                validation_exit_code=validation_exit_code,
                notes=notes,
            )

        plan = self._run_step(
            WorkflowState.DRAFT_PLAN,
            lambda step: self._model_call(
                WorkflowState.DRAFT_PLAN,
                {
                    "task": input_model.task,
                    "classification": classification,
                    "citations": _citation_payload(context_bundles),
                },
            ),
        )
        risk = self._run_step(
            WorkflowState.RISK_ASSESSMENT,
            lambda step: self._model_call(
                WorkflowState.RISK_ASSESSMENT,
                {
                    "task": input_model.task,
                    "classification": classification,
                    "plan": plan,
                    "citations": _citation_payload(context_bundles),
                },
            ),
        )

        approval_required = _bool_value(risk, "approval_required") or (
            self.policy.config.permission_level < PermissionLevel.WRITE_WORKSPACE
        )
        self._run_step(
            WorkflowState.APPROVAL_IF_NEEDED,
            lambda step: self._handle_approval_step(step, approval_required),
        )
        if approval_required:
            status = WorkflowStatus.WAITING_APPROVAL
            stop_reason = WorkflowStopReason.APPROVAL_REQUIRED
            notes.append("human approval is required before workspace mutation")
            return self._finish(
                input_model=input_model,
                status=status,
                stop_reason=stop_reason,
                approval_required=True,
                policy_blocked=policy_blocked,
                context_bundles=context_bundles,
                changed_files=sorted(changed_files),
                patch_attempts=patch_attempts,
                validation_runs=validation_runs,
                tests_ran=tests_ran,
                tests_passed=tests_passed,
                validation_exit_code=validation_exit_code,
                notes=notes,
            )

        validation_command = input_model.validation_command or self.config.validation_command
        for attempt in range(1, self.config.max_patch_attempts + 1):
            patch_attempts = attempt
            patch_state = (
                WorkflowState.GENERATE_PATCH if attempt == 1 else WorkflowState.REVISE_PATCH_LIMITED
            )
            patch_payload = self._run_step(
                patch_state,
                partial(
                    self._generate_patch_payload,
                    patch_state,
                    input_model.task,
                    plan,
                    risk,
                    context_bundles,
                    last_failure_signature,
                    attempt,
                ),
            )
            patch = _patch_from_payload(patch_payload)
            changed_files.add(patch.path.as_posix())

            proposed = self._run_step(
                WorkflowState.GENERATE_PATCH
                if attempt == 1
                else WorkflowState.REVISE_PATCH_LIMITED,
                partial(self._propose_patch_step, patch),
                record_state=False,
            )
            if not proposed.success:
                policy_blocked = _is_policy_denied(proposed.error)
                status = WorkflowStatus.STOPPED
                stop_reason = (
                    WorkflowStopReason.POLICY_BLOCKED
                    if policy_blocked
                    else WorkflowStopReason.PATCH_MISMATCH
                )
                notes.append(_tool_error_message(proposed.error))
                break

            applied = self._run_step(
                WorkflowState.APPLY_PATCH_WORKSPACE,
                partial(self._apply_patch_step, patch, input_model.base_branch),
            )
            if not applied.success:
                policy_blocked = _is_policy_denied(applied.error)
                approval_required = _is_approval_required(applied.error)
                status = (
                    WorkflowStatus.WAITING_APPROVAL if approval_required else WorkflowStatus.STOPPED
                )
                stop_reason = (
                    WorkflowStopReason.APPROVAL_REQUIRED
                    if approval_required
                    else WorkflowStopReason.POLICY_BLOCKED
                    if policy_blocked
                    else WorkflowStopReason.PATCH_MISMATCH
                )
                notes.append(_tool_error_message(applied.error))
                break

            if validation_command is None:
                tests_ran = False
                tests_passed = None
                notes.append("validation command was not configured")
                status = WorkflowStatus.COMPLETED
                break

            validation = self._run_step(
                WorkflowState.RUN_VALIDATION,
                lambda step: self._tools(step).run_validation_command(
                    RunValidationCommandInput(
                        command=validation_command,
                        timeout_seconds=self.config.validation_timeout_seconds,
                    )
                ),
            )
            if not validation.success and _is_approval_required(validation.error):
                approval_required = True
                status = WorkflowStatus.WAITING_APPROVAL
                stop_reason = WorkflowStopReason.APPROVAL_REQUIRED
                notes.append(_tool_error_message(validation.error))
                break
            tests_ran = True
            validation_runs += 1
            validation_exit_code = validation.exit_code
            tests_passed = validation.success and validation.exit_code == 0
            if tests_passed:
                status = WorkflowStatus.COMPLETED
                break

            failure_signature = _failure_signature(validation.stdout, validation.stderr)
            analysis = self._run_step(
                WorkflowState.ANALYZE_FAILURES,
                partial(
                    self._analyze_failure_step,
                    input_model.task,
                    attempt,
                    validation.exit_code,
                    failure_signature,
                ),
            )
            last_failure_signature = _str_value(
                analysis, "failure_signature", default=failure_signature
            )
            if failure_signature in failure_signatures:
                status = WorkflowStatus.FAILED
                stop_reason = WorkflowStopReason.REPEATED_FAILURE
                notes.append("validation produced the same failure signature twice")
                break
            failure_signatures.add(failure_signature)
        else:
            status = WorkflowStatus.FAILED
            stop_reason = WorkflowStopReason.MAX_PATCH_ATTEMPTS
            notes.append("maximum automatic patch attempts reached")

        if status is WorkflowStatus.COMPLETED:
            self._run_step(
                WorkflowState.REVIEW_DIFF,
                lambda step: self._review_diff(step, input_model.task),
            )
            stop_reason = None
        elif stop_reason is None:
            stop_reason = WorkflowStopReason.VALIDATION_FAILED

        return self._finish(
            input_model=input_model,
            status=status,
            stop_reason=stop_reason,
            approval_required=approval_required,
            policy_blocked=policy_blocked,
            context_bundles=context_bundles,
            changed_files=sorted(changed_files),
            patch_attempts=patch_attempts,
            validation_runs=validation_runs,
            tests_ran=tests_ran,
            tests_passed=tests_passed,
            validation_exit_code=validation_exit_code,
            notes=notes,
        )

    def _run_step(
        self,
        state: WorkflowState,
        action: Callable[[AgentStep], T],
        *,
        record_state: bool = True,
    ) -> T:
        step = self._create_step(state, record_state=record_state)
        self.runs.transition_step(step=step, status=AgentStepStatus.RUNNING)
        try:
            result = action(step)
        except Exception as exc:
            step.summary = f"{state.value} failed: {exc}"
            self.runs.transition_step(step=step, status=AgentStepStatus.FAILED)
            raise
        step.summary = _step_summary(state, result)
        self.runs.transition_step(step=step, status=AgentStepStatus.COMPLETED)
        return result

    def _create_step(self, state: WorkflowState, *, record_state: bool) -> AgentStep:
        if record_state:
            self._states.append(state)
        self._sequence += 1
        return self.runs.create_step(
            agent_run_id=self.agent_run_id,
            sequence=self._sequence,
            name=state.value,
        )

    def _tools(self, step: AgentStep) -> ToolRegistry:
        return ToolRegistry(
            session=self.session,
            policy=self.policy,
            context=ToolContext(
                agent_run_id=self.agent_run_id,
                agent_step_id=step.id,
                workspace_path=self.workspace_path,
                actor_user_id=self.actor_user_id,
            ),
            indexer=self.indexer,
            retrieval_engine=self.retrieval_engine,
            sandbox_runner=self.sandbox_runner,
        )

    def _model_call(
        self,
        state: WorkflowState,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        started = time.monotonic()
        response = self.model.complete(state=state, payload=payload)
        duration_ms = int((time.monotonic() - started) * 1000)
        self.audit.record(
            event_type="model.call",
            summary=f"model call recorded: state={state.value} duration_ms={duration_ms}",
            subject_type="workflow_state",
            subject_id=state.value,
            actor_user_id=self.actor_user_id,
            agent_run_id=self.agent_run_id,
        )
        return response

    def _handle_approval_step(self, step: AgentStep, approval_required: bool) -> str:
        if not approval_required:
            return "approval not required"
        output = self._tools(step).request_approval(
            RequestApprovalInput(
                requested_action="workspace_mutation",
                risk_level="high",
                reason="Human approval required before workspace mutation",
            )
        )
        if not output.success:
            return _tool_error_message(output.error)
        return f"approval requested: {output.approval_request_id}"

    def _generate_patch_payload(
        self,
        state: WorkflowState,
        task: str,
        plan: Mapping[str, object],
        risk: Mapping[str, object],
        context_bundles: Sequence[ContextBundleOutput],
        previous_failure_signature: str | None,
        attempt: int,
        _step: AgentStep,
    ) -> Mapping[str, object]:
        return self._model_call(
            state,
            {
                "task": task,
                "plan": plan,
                "risk": risk,
                "citations": _citation_payload(context_bundles),
                "previous_failure_signature": previous_failure_signature,
                "attempt": attempt,
            },
        )

    def _propose_patch_step(
        self,
        patch: PatchInstruction,
        step: AgentStep,
    ) -> ProposePatchOutput:
        return self._tools(step).propose_patch(
            ProposePatchInput(
                path=patch.path,
                original_text=patch.original_text,
                replacement_text=patch.replacement_text,
            )
        )

    def _apply_patch_step(
        self,
        patch: PatchInstruction,
        branch: str | None,
        step: AgentStep,
    ) -> ApplyPatchOutput:
        return self._tools(step).apply_patch_to_workspace(
            ApplyPatchInput(
                path=patch.path,
                original_text=patch.original_text,
                replacement_text=patch.replacement_text,
                branch=branch,
            )
        )

    def _analyze_failure_step(
        self,
        task: str,
        attempt: int,
        exit_code: int | None,
        failure_signature: str,
        _step: AgentStep,
    ) -> Mapping[str, object]:
        return self._model_call(
            WorkflowState.ANALYZE_FAILURES,
            {
                "task": task,
                "attempt": attempt,
                "exit_code": exit_code,
                "failure_signature": failure_signature,
            },
        )

    def _review_diff(self, step: AgentStep, task: str) -> Mapping[str, object]:
        tools = self._tools(step)
        diff = tools.get_git_diff(GetGitDiffInput())
        summary = tools.summarize_diff(SummarizeDiffInput(diff=diff.diff))
        return self._model_call(
            WorkflowState.REVIEW_DIFF,
            {
                "task": task,
                "diff_summary": summary.model_dump(mode="json"),
                "diff_available": diff.success,
            },
        )

    def _context_confident(self, bundles: Sequence[ContextBundleOutput]) -> bool:
        if not bundles:
            return False
        return max(bundle.score for bundle in bundles) >= self.config.context_min_score

    def _finish(
        self,
        *,
        input_model: WorkflowInput,
        status: WorkflowStatus,
        stop_reason: WorkflowStopReason | None,
        approval_required: bool,
        policy_blocked: bool,
        context_bundles: Sequence[ContextBundleOutput],
        changed_files: list[str],
        patch_attempts: int,
        validation_runs: int,
        tests_ran: bool,
        tests_passed: bool | None,
        validation_exit_code: int | None,
        notes: list[str],
    ) -> WorkflowResult:
        report = WorkflowFinalReport(
            status=status,
            task=input_model.task,
            summary=_report_summary(status, stop_reason, tests_ran, tests_passed),
            stop_reason=stop_reason,
            approval_required=approval_required,
            policy_blocked=policy_blocked,
            files_cited=_citations(context_bundles),
            files_changed=changed_files,
            patch_attempts=patch_attempts,
            tests_ran=tests_ran,
            tests_passed=tests_passed,
            validation_command=input_model.validation_command or self.config.validation_command,
            validation_exit_code=validation_exit_code,
            notes=notes,
        )
        self._run_step(WorkflowState.FINAL_REPORT, lambda step: report)
        self._transition_final_run_status(status)
        return WorkflowResult(
            status=status,
            states=list(self._states),
            patch_attempts=patch_attempts,
            validation_runs=validation_runs,
            final_report=report,
        )

    def _ensure_run_running(self) -> None:
        run = self.runs.runs.get(self.agent_run_id)
        if run is not None and AgentRunStatus(run.status) is AgentRunStatus.PENDING:
            self.runs.transition_run(agent_run_id=self.agent_run_id, status=AgentRunStatus.RUNNING)

    def _transition_final_run_status(self, status: WorkflowStatus) -> None:
        run = self.runs.runs.get(self.agent_run_id)
        if run is None:
            return
        current = AgentRunStatus(run.status)
        if current is AgentRunStatus.WAITING_APPROVAL:
            return
        if current is not AgentRunStatus.RUNNING:
            return
        final_status = AgentRunStatus.FAILED
        if status is WorkflowStatus.COMPLETED:
            final_status = AgentRunStatus.COMPLETED
        self.runs.transition_run(agent_run_id=self.agent_run_id, status=final_status)


def _patch_from_payload(payload: Mapping[str, object]) -> PatchInstruction:
    return PatchInstruction(
        path=Path(_str_value(payload, "path")),
        original_text=_str_value(payload, "original_text"),
        replacement_text=_str_value(payload, "replacement_text"),
    )


def _citation_payload(bundles: Sequence[ContextBundleOutput]) -> list[dict[str, object]]:
    return [
        {
            "path": bundle.path,
            "start_line": bundle.start_line,
            "end_line": bundle.end_line,
            "reasons": bundle.reasons,
            "score": bundle.score,
        }
        for bundle in bundles
    ]


def _citations(bundles: Sequence[ContextBundleOutput]) -> list[WorkflowCitation]:
    return [
        WorkflowCitation(
            path=bundle.path,
            start_line=bundle.start_line,
            end_line=bundle.end_line,
            reasons=bundle.reasons,
        )
        for bundle in bundles
    ]


def _bool_value(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    return value is True


def _str_value(payload: Mapping[str, object], key: str, *, default: str | None = None) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"model response field '{key}' must be a string")
    return value


def _failure_signature(stdout: str, stderr: str) -> str:
    combined = "\n".join(line.strip() for line in (stdout + "\n" + stderr).splitlines())
    if len(combined) > FAILURE_SIGNATURE_CHARS:
        return combined[-FAILURE_SIGNATURE_CHARS:]
    return combined


def _tool_error_message(error: object) -> str:
    if error is None:
        return "tool failed without a structured error"
    code = getattr(error, "code", "tool_error")
    message = getattr(error, "message", str(error))
    return f"{code}: {message}"


def _is_policy_denied(error: object) -> bool:
    return getattr(error, "code", None) == "policy_denied"


def _is_approval_required(error: object) -> bool:
    return getattr(error, "code", None) == "approval_required"


def _step_summary(state: WorkflowState, result: object) -> str:
    if isinstance(result, BaseModel):
        dumped = result.model_dump()
        if "success" in dumped:
            return f"{state.value} completed success={dumped['success']}"
        return f"{state.value} completed"
    if isinstance(result, Mapping):
        return f"{state.value} completed with structured model output"
    return str(result)[:500]


def _report_summary(
    status: WorkflowStatus,
    stop_reason: WorkflowStopReason | None,
    tests_ran: bool,
    tests_passed: bool | None,
) -> str:
    if status is WorkflowStatus.COMPLETED:
        if tests_ran and tests_passed:
            return "workflow completed and configured validation passed"
        if tests_ran:
            return "workflow completed but validation did not pass"
        return "workflow completed without configured validation"
    if status is WorkflowStatus.WAITING_APPROVAL:
        return "workflow stopped for human approval"
    if stop_reason is not None:
        return f"workflow stopped: {stop_reason.value}"
    return f"workflow ended with status {status.value}"
