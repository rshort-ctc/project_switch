from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.repositories import PolicyDecisionRepository
from app.models.entities import PolicyDecision
from app.models.enums import PolicyDecisionResult
from app.security.redaction import contains_secret, redact_secrets
from app.services.audit import AuditService


class PermissionLevel(IntEnum):
    READ_ONLY_QA = 0
    PLAN_ONLY = 1
    PROPOSE_PATCH = 2
    WRITE_WORKSPACE = 3
    SANDBOX_COMMANDS = 4
    BRANCH_ARTIFACT = 5
    ADMIN_RESERVED = 6


class PolicyOperation(StrEnum):
    READ_PATH = "read_path"
    PLAN = "plan"
    PROPOSE_PATCH = "propose_patch"
    WRITE_FILE = "write_file"
    RUN_COMMAND = "run_command"
    CREATE_BRANCH_ARTIFACT = "create_branch_artifact"
    PUSH = "push"
    MERGE = "merge"
    MODIFY_POLICY = "modify_policy"


class PolicyViolation(ValueError):
    pass


@dataclass(frozen=True)
class PolicyConfig:
    workspace_path: Path
    permission_level: PermissionLevel
    allowed_commands: tuple[tuple[str, ...], ...] = (
        ("pytest",),
        ("ruff", "check"),
        ("ruff", "format"),
        ("mypy",),
        ("alembic", "upgrade"),
    )
    path_allowlist: tuple[Path, ...] = ()
    protected_branches: tuple[str, ...] = ("main", "master", "release", "production")
    secret_path_patterns: tuple[str, ...] = (
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "*secret*",
        "*credentials*",
    )
    policy_paths: tuple[str, ...] = (
        "app/security/",
        "AGENTS.md",
        ".env.example",
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_path", self.workspace_path.resolve())
        if not self.path_allowlist:
            object.__setattr__(self, "path_allowlist", (self.workspace_path,))
        else:
            object.__setattr__(
                self,
                "path_allowlist",
                tuple(path.resolve() for path in self.path_allowlist),
            )


@dataclass(frozen=True)
class PolicyRequest:
    operation: PolicyOperation
    path: Path | None = None
    command: tuple[str, ...] = ()
    branch: str | None = None
    requires_sandbox: bool = True
    human_approved: bool = False
    content_summary: str | None = None
    agent_run_id: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: PolicyDecisionResult
    policy_name: str
    reason: str
    approval_required: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecisionResult.ALLOWED


class PolicyEngine:
    def __init__(self, config: PolicyConfig, session: Session | None = None) -> None:
        self.config = config
        self.session = session
        self.decisions = PolicyDecisionRepository(session) if session is not None else None
        self.audit = AuditService(session) if session is not None else None

    def evaluate(self, request: PolicyRequest) -> PolicyEvaluation:
        evaluation = self._evaluate(request)
        self._record(request, evaluation)
        return evaluation

    def assert_allowed(self, request: PolicyRequest) -> PolicyEvaluation:
        evaluation = self.evaluate(request)
        if not evaluation.allowed:
            raise PolicyViolation(evaluation.reason)
        return evaluation

    def approval_required(self, request: PolicyRequest) -> bool:
        return self.evaluate(request).approval_required

    def _evaluate(self, request: PolicyRequest) -> PolicyEvaluation:  # noqa: PLR0911
        if self.config.permission_level >= PermissionLevel.ADMIN_RESERVED:
            return _denied(
                "admin_reserved",
                "level 6 is reserved for administrators and cannot be used autonomously",
            )

        minimum_level = _minimum_level(request.operation)
        if minimum_level is None:
            return _denied(
                "deny_by_default", f"operation '{request.operation}' is not allowed by policy"
            )
        if self.config.permission_level < minimum_level:
            return _denied(
                "insufficient_permission",
                f"operation '{request.operation}' requires level {minimum_level}; "
                f"current level is {self.config.permission_level}",
            )

        if request.operation is PolicyOperation.READ_PATH:
            return self._evaluate_path_read(request)
        if request.operation is PolicyOperation.PLAN:
            return _allowed("plan_allowed", "planning is allowed")
        if request.operation is PolicyOperation.PROPOSE_PATCH:
            return self._evaluate_patch_proposal(request)
        if request.operation is PolicyOperation.WRITE_FILE:
            return self._evaluate_write(request)
        if request.operation is PolicyOperation.RUN_COMMAND:
            return self._evaluate_command(request)
        if request.operation is PolicyOperation.CREATE_BRANCH_ARTIFACT:
            return self._evaluate_branch_artifact(request)
        if request.operation in {PolicyOperation.PUSH, PolicyOperation.MERGE}:
            return _denied(
                "push_merge_denied",
                "push and merge operations are never autonomous; "
                "use human-controlled release tooling",
            )
        if request.operation is PolicyOperation.MODIFY_POLICY:
            return _denied("policy_immutable", "tasks cannot modify or weaken policy files")

        return _denied(
            "deny_by_default", f"operation '{request.operation}' is not allowed by policy"
        )

    def _evaluate_path_read(self, request: PolicyRequest) -> PolicyEvaluation:
        path_result = self._validate_path(request.path)
        if path_result is not None:
            return path_result
        if request.path is not None and self._is_secret_path(request.path):
            return _denied(
                "secret_read_denied", f"secret path is not readable by default: {request.path}"
            )
        return _allowed("read_allowed", "path read is allowed")

    def _evaluate_patch_proposal(self, request: PolicyRequest) -> PolicyEvaluation:
        if request.path is not None:
            path_result = self._validate_path(request.path)
            if path_result is not None:
                return path_result
            if self._is_secret_path(request.path):
                return _denied(
                    "secret_patch_denied", f"secret path cannot be proposed: {request.path}"
                )
        return _allowed("patch_proposal_allowed", "patch proposal is allowed without writing files")

    def _evaluate_write(self, request: PolicyRequest) -> PolicyEvaluation:
        path_result = self._validate_path(request.path)
        if path_result is not None:
            return path_result
        if request.path is not None and self._is_secret_path(request.path):
            return _denied("secret_write_denied", f"secret path is not writable: {request.path}")
        if request.path is not None and self._is_policy_path(request.path):
            return _denied("policy_immutable", "tasks cannot modify or weaken policy files")
        if request.content_summary and contains_secret(request.content_summary):
            return _denied(
                "secret_write_denied", "write content summary appears to contain a secret"
            )
        if request.branch in self.config.protected_branches:
            return _denied(
                "protected_branch", f"cannot write to protected branch '{request.branch}'"
            )
        return _allowed("workspace_write_allowed", "write is allowed inside the isolated workspace")

    def _evaluate_command(self, request: PolicyRequest) -> PolicyEvaluation:
        if not request.requires_sandbox:
            return _denied("sandbox_required", "commands must run through the sandbox")
        if not request.command:
            return _denied("command_required", "command requests must provide an argument list")
        if _contains_shell_passthrough(request.command):
            return _denied(
                "shell_passthrough_denied",
                "shell passthrough and shell metacharacters are not allowed",
            )
        if not self._command_allowed(request.command):
            return _denied(
                "command_not_allowlisted",
                f"command is not allowlisted: {' '.join(request.command)}",
            )
        return _allowed("command_allowlisted", "allowed validation command may run in sandbox")

    def _evaluate_branch_artifact(self, request: PolicyRequest) -> PolicyEvaluation:
        if request.branch in self.config.protected_branches:
            return _denied(
                "protected_branch",
                f"cannot create artifacts targeting protected branch '{request.branch}'",
            )
        if not request.human_approved:
            return PolicyEvaluation(
                decision=PolicyDecisionResult.REQUIRES_APPROVAL,
                policy_name="approval_required",
                reason="branch or PR artifacts require human approval",
                approval_required=True,
            )
        return _allowed(
            "branch_artifact_allowed", "human-approved branch or PR artifact creation is allowed"
        )

    def _validate_path(self, path: Path | None) -> PolicyEvaluation | None:
        if path is None:
            return _denied("path_required", "operation requires a path")
        resolved = (
            (self.config.workspace_path / path).resolve()
            if not path.is_absolute()
            else path.resolve()
        )
        if not any(_is_relative_to(resolved, allowed) for allowed in self.config.path_allowlist):
            return _denied(
                "path_outside_workspace", f"path is outside the allowed workspace: {path}"
            )
        return None

    def _command_allowed(self, command: tuple[str, ...]) -> bool:
        return any(command[: len(allowed)] == allowed for allowed in self.config.allowed_commands)

    def _is_secret_path(self, path: Path) -> bool:
        return any(
            path.match(pattern) or path.name == pattern
            for pattern in self.config.secret_path_patterns
        )

    def _is_policy_path(self, path: Path) -> bool:
        relative = self._relative_path(path)
        return any(
            relative == policy_path or relative.startswith(policy_path)
            for policy_path in self.config.policy_paths
        )

    def _relative_path(self, path: Path) -> str:
        resolved = (
            (self.config.workspace_path / path).resolve()
            if not path.is_absolute()
            else path.resolve()
        )
        try:
            return resolved.relative_to(self.config.workspace_path).as_posix()
        except ValueError:
            return resolved.as_posix()

    def _record(
        self, request: PolicyRequest, evaluation: PolicyEvaluation
    ) -> PolicyDecision | None:
        if self.decisions is None:
            return None
        decision = self.decisions.create(
            decision=evaluation.decision,
            policy_name=evaluation.policy_name,
            reason=redact_secrets(evaluation.reason) or evaluation.reason,
            enforced=True,
            agent_run_id=request.agent_run_id,
            tool_call_id=request.tool_call_id,
        )
        if self.audit is not None:
            self.audit.record(
                event_type="policy.evaluated",
                summary=f"policy {evaluation.policy_name}: {evaluation.decision}",
                subject_type="policy_decision",
                subject_id=decision.id,
                agent_run_id=request.agent_run_id,
            )
        return decision


def _minimum_level(operation: PolicyOperation) -> PermissionLevel | None:
    levels = {
        PolicyOperation.READ_PATH: PermissionLevel.READ_ONLY_QA,
        PolicyOperation.PLAN: PermissionLevel.PLAN_ONLY,
        PolicyOperation.PROPOSE_PATCH: PermissionLevel.PROPOSE_PATCH,
        PolicyOperation.WRITE_FILE: PermissionLevel.WRITE_WORKSPACE,
        PolicyOperation.RUN_COMMAND: PermissionLevel.SANDBOX_COMMANDS,
        PolicyOperation.CREATE_BRANCH_ARTIFACT: PermissionLevel.BRANCH_ARTIFACT,
        PolicyOperation.PUSH: PermissionLevel.ADMIN_RESERVED,
        PolicyOperation.MERGE: PermissionLevel.ADMIN_RESERVED,
        PolicyOperation.MODIFY_POLICY: PermissionLevel.ADMIN_RESERVED,
    }
    return levels.get(operation)


def _allowed(policy_name: str, reason: str) -> PolicyEvaluation:
    return PolicyEvaluation(
        decision=PolicyDecisionResult.ALLOWED, policy_name=policy_name, reason=reason
    )


def _denied(policy_name: str, reason: str) -> PolicyEvaluation:
    return PolicyEvaluation(
        decision=PolicyDecisionResult.DENIED, policy_name=policy_name, reason=reason
    )


def _contains_shell_passthrough(command: tuple[str, ...]) -> bool:
    shell_names = {"bash", "sh", "zsh", "fish", "powershell", "pwsh", "python", "python3"}
    metacharacters = {";", "&&", "||", "|", "`", "$(", ">", "<"}
    if command[0] in shell_names:
        return True
    joined = " ".join(command)
    return any(token in joined for token in metacharacters)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
