import difflib
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.repositories import PatchArtifactRepository
from app.patches.types import (
    FileDiffMetadata,
    PatchApplyResult,
    PatchFileStatus,
    PatchMetadata,
    PatchRiskCategory,
)
from app.services.audit import AuditService

BINARY_MARKERS = ("GIT binary patch", "Binary files ")
LARGE_DELETION_LINES = 200
HUNK_HEADER_PATTERN = re.compile(
    r"@@ -(?P<old_start>\d+)(,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(,(?P<new_count>\d+))? @@"
)


class PatchRejected(ValueError):
    pass


@dataclass
class HunkLine:
    marker: str
    text: str


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[HunkLine] = field(default_factory=list)


@dataclass
class ParsedFilePatch:
    old_path: str | None
    new_path: str | None
    hunks: list[Hunk] = field(default_factory=list)
    is_binary: bool = False

    @property
    def target_path(self) -> str:
        if self.new_path is not None:
            return self.new_path
        if self.old_path is not None:
            return self.old_path
        raise PatchRejected("patch file header did not include a target path")

    @property
    def status(self) -> PatchFileStatus:
        if self.old_path is None:
            return PatchFileStatus.ADDED
        if self.new_path is None:
            return PatchFileStatus.DELETED
        return PatchFileStatus.MODIFIED


class PatchService:
    def __init__(
        self,
        *,
        session: Session,
        workspace_path: Path,
        agent_run_id: str,
        actor_user_id: str | None = None,
    ) -> None:
        self.session = session
        self.workspace_path = workspace_path.resolve()
        self.agent_run_id = agent_run_id
        self.actor_user_id = actor_user_id
        self.patch_artifacts = PatchArtifactRepository(session)
        self.audit = AuditService(session)

    def generate_unified_diff(self, path: Path, original: str, replacement: str) -> str:
        self._validate_relative_path(path.as_posix())
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                replacement.splitlines(keepends=True),
                fromfile=f"a/{path.as_posix()}",
                tofile=f"b/{path.as_posix()}",
            )
        )
        self.audit.record(
            event_type="patch.diff_generated",
            summary=f"generated unified diff for {path.as_posix()}",
            subject_type="patch",
            subject_id=None,
            actor_user_id=self.actor_user_id,
            agent_run_id=self.agent_run_id,
        )
        return diff

    def analyze_diff(self, diff: str, *, allow_binary: bool = False) -> PatchMetadata:
        parsed = self._parse_diff(diff)
        metadata = self._metadata(parsed)
        if metadata.is_binary and not allow_binary:
            self._audit_rejected("binary patches are disabled")
            raise PatchRejected("binary patches are disabled unless explicitly allowed")
        self.audit.record(
            event_type="patch.analyzed",
            summary=metadata.human_summary,
            subject_type="patch",
            subject_id=None,
            actor_user_id=self.actor_user_id,
            agent_run_id=self.agent_run_id,
        )
        return metadata

    def store_patch_artifact(
        self,
        *,
        diff: str,
        metadata: PatchMetadata,
        name: str = "patch",
    ) -> tuple[str, str]:
        digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        root = self.workspace_path / ".switch" / "patches"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{name}-{digest}.patch"
        path.write_text(diff, encoding="utf-8")
        artifact = self.patch_artifacts.create(
            agent_run_id=self.agent_run_id,
            diff_summary=metadata.human_summary,
            diff_sha256=digest,
            storage_path=path.relative_to(self.workspace_path).as_posix(),
        )
        self.audit.record(
            event_type="patch.artifact_stored",
            summary=f"stored patch artifact: {artifact.id}",
            subject_type="patch_artifact",
            subject_id=artifact.id,
            actor_user_id=self.actor_user_id,
            agent_run_id=self.agent_run_id,
        )
        return artifact.id, artifact.storage_path

    def apply_patch(
        self,
        *,
        diff: str,
        human_approved: bool = False,
        allow_binary: bool = False,
    ) -> PatchApplyResult:
        parsed = self._parse_diff(diff)
        metadata = self._metadata(parsed)
        if metadata.is_binary and not allow_binary:
            self._audit_rejected("binary patches are disabled")
            raise PatchRejected("binary patches are disabled unless explicitly allowed")
        if metadata.approval_required and not human_approved:
            self._audit_rejected("high-risk patch requires human approval")
            raise PatchRejected("high-risk patch requires human approval before workspace apply")

        before = self._read_before(parsed)
        patch_id, patch_path = self.store_patch_artifact(diff=diff, metadata=metadata)
        for file_patch in parsed:
            self._apply_file_patch(file_patch)
        after = {path: self._read_optional(path) for path in before}
        rollback = self._rollback_patch(before, after)
        rollback_metadata = (
            self._metadata(self._parse_diff(rollback)) if rollback else PatchMetadata()
        )
        rollback_id = None
        rollback_path = None
        if rollback:
            rollback_id, rollback_path = self.store_patch_artifact(
                diff=rollback,
                metadata=rollback_metadata,
                name="rollback",
            )
            self.audit.record(
                event_type="patch.rollback_generated",
                summary="generated rollback patch",
                subject_type="patch_artifact",
                subject_id=rollback_id,
                actor_user_id=self.actor_user_id,
                agent_run_id=self.agent_run_id,
            )
        self.audit.record(
            event_type="patch.applied",
            summary=metadata.human_summary,
            subject_type="patch_artifact",
            subject_id=patch_id,
            actor_user_id=self.actor_user_id,
            agent_run_id=self.agent_run_id,
        )
        return PatchApplyResult(
            applied=True,
            metadata=metadata,
            rollback_patch=rollback,
            patch_artifact_id=patch_id,
            patch_artifact_path=patch_path,
            rollback_artifact_id=rollback_id,
            rollback_artifact_path=rollback_path,
        )

    def _parse_diff(self, diff: str) -> list[ParsedFilePatch]:  # noqa: PLR0912
        if "\x00" in diff:
            self._audit_rejected("patch contains NUL bytes")
            raise PatchRejected("binary patch payload contains NUL bytes")
        lines = diff.splitlines()
        parsed: list[ParsedFilePatch] = []
        current: ParsedFilePatch | None = None
        current_hunk: Hunk | None = None

        for line in lines:
            if line.startswith("diff --git "):
                if current is not None:
                    parsed.append(current)
                current = ParsedFilePatch(old_path=None, new_path=None)
                current_hunk = None
                continue
            if any(line.startswith(marker) for marker in BINARY_MARKERS):
                if current is None:
                    current = ParsedFilePatch(old_path=None, new_path=None)
                current.is_binary = True
                continue
            if line.startswith("--- "):
                has_existing_header = current is not None and (
                    current.old_path is not None or current.new_path is not None
                )
                if has_existing_header:
                    assert current is not None
                    parsed.append(current)
                    current = ParsedFilePatch(old_path=None, new_path=None)
                    current_hunk = None
                if current is None:
                    current = ParsedFilePatch(old_path=None, new_path=None)
                current.old_path = self._clean_diff_path(line.removeprefix("--- ").strip())
                continue
            if line.startswith("+++ "):
                if current is None:
                    current = ParsedFilePatch(old_path=None, new_path=None)
                current.new_path = self._clean_diff_path(line.removeprefix("+++ ").strip())
                continue
            if line.startswith("@@ "):
                if current is None:
                    raise PatchRejected("hunk appeared before file header")
                current_hunk = _parse_hunk_header(line)
                current.hunks.append(current_hunk)
                continue
            if current_hunk is not None and line:
                marker = line[0]
                if marker in {" ", "+", "-", "\\"}:
                    current_hunk.lines.append(HunkLine(marker=marker, text=line[1:]))

        if current is not None:
            parsed.append(current)
        if not parsed:
            raise PatchRejected("patch did not contain any file diffs")
        for file_patch in parsed:
            self._validate_file_patch(file_patch)
        return parsed

    def _metadata(self, parsed: list[ParsedFilePatch]) -> PatchMetadata:
        files: list[FileDiffMetadata] = []
        risk_categories: set[PatchRiskCategory] = set()
        changed_files: list[str] = []
        added_files: list[str] = []
        deleted_files: list[str] = []
        total_added = 0
        total_deleted = 0

        for file_patch in parsed:
            added = sum(1 for hunk in file_patch.hunks for line in hunk.lines if line.marker == "+")
            deleted = sum(
                1 for hunk in file_patch.hunks for line in hunk.lines if line.marker == "-"
            )
            path = file_patch.target_path
            categories = _risk_categories(path, added, deleted)
            risk_categories.update(categories)
            file_metadata = FileDiffMetadata(
                path=path,
                old_path=file_patch.old_path,
                status=file_patch.status,
                added_lines=added,
                deleted_lines=deleted,
                is_binary=file_patch.is_binary,
                high_risk_categories=sorted(categories),
            )
            files.append(file_metadata)
            changed_files.append(path)
            total_added += added
            total_deleted += deleted
            if file_patch.status is PatchFileStatus.ADDED:
                added_files.append(path)
            if file_patch.status is PatchFileStatus.DELETED:
                deleted_files.append(path)

        return PatchMetadata(
            files=files,
            changed_files=sorted(set(changed_files)),
            added_files=sorted(set(added_files)),
            deleted_files=sorted(set(deleted_files)),
            total_added_lines=total_added,
            total_deleted_lines=total_deleted,
            is_binary=any(file.is_binary for file in files),
            high_risk_categories=sorted(risk_categories),
            approval_required=bool(risk_categories),
            human_summary=_human_summary(files, risk_categories),
        )

    def _validate_file_patch(self, file_patch: ParsedFilePatch) -> None:
        if file_patch.old_path is None and file_patch.new_path is None:
            raise PatchRejected("patch file is missing ---/+++ headers")
        if file_patch.old_path is not None:
            self._validate_relative_path(file_patch.old_path)
        if file_patch.new_path is not None:
            self._validate_relative_path(file_patch.new_path)

    def _validate_relative_path(self, path: str) -> None:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            self._audit_rejected(f"path escapes workspace: {path}")
            raise PatchRejected(f"patch path escapes workspace: {path}")
        resolved = (self.workspace_path / relative).resolve()
        try:
            resolved.relative_to(self.workspace_path)
        except ValueError as exc:
            self._audit_rejected(f"path escapes workspace: {path}")
            raise PatchRejected(f"patch path escapes workspace: {path}") from exc

    def _clean_diff_path(self, value: str) -> str | None:
        path = value.split("\t", maxsplit=1)[0]
        if path == "/dev/null":
            return None
        if path.startswith("a/") or path.startswith("b/"):
            path = path[2:]
        self._validate_relative_path(path)
        return path

    def _read_before(self, parsed: list[ParsedFilePatch]) -> dict[str, str | None]:
        before: dict[str, str | None] = {}
        for file_patch in parsed:
            path = file_patch.target_path
            before[path] = self._read_optional(path)
        return before

    def _read_optional(self, path: str) -> str | None:
        resolved = (self.workspace_path / path).resolve()
        if not resolved.exists():
            return None
        return resolved.read_text(encoding="utf-8", errors="ignore")

    def _apply_file_patch(self, file_patch: ParsedFilePatch) -> None:
        path = (self.workspace_path / file_patch.target_path).resolve()
        original_text = (
            "" if file_patch.old_path is None else self._read_optional(file_patch.target_path)
        )
        if original_text is None:
            raise PatchRejected(f"target file does not exist: {file_patch.target_path}")
        original_lines = original_text.splitlines()
        patched_lines: list[str] = []
        source_index = 0

        for hunk in file_patch.hunks:
            hunk_start = max(hunk.old_start - 1, 0)
            patched_lines.extend(original_lines[source_index:hunk_start])
            source_index = hunk_start
            for hunk_line in hunk.lines:
                if hunk_line.marker == " ":
                    _require_line(
                        original_lines,
                        source_index,
                        hunk_line.text,
                        file_patch.target_path,
                    )
                    patched_lines.append(original_lines[source_index])
                    source_index += 1
                elif hunk_line.marker == "-":
                    _require_line(
                        original_lines,
                        source_index,
                        hunk_line.text,
                        file_patch.target_path,
                    )
                    source_index += 1
                elif hunk_line.marker == "+":
                    patched_lines.append(hunk_line.text)

        patched_lines.extend(original_lines[source_index:])
        if file_patch.new_path is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(patched_lines) + "\n", encoding="utf-8")

    def _rollback_patch(self, before: dict[str, str | None], after: dict[str, str | None]) -> str:
        chunks: list[str] = []
        for path in sorted(before):
            old = after[path]
            new = before[path]
            old_lines = [] if old is None else old.splitlines(keepends=True)
            new_lines = [] if new is None else new.splitlines(keepends=True)
            fromfile = "/dev/null" if old is None else f"a/{path}"
            tofile = "/dev/null" if new is None else f"b/{path}"
            chunks.append(
                "".join(
                    difflib.unified_diff(
                        old_lines,
                        new_lines,
                        fromfile=fromfile,
                        tofile=tofile,
                    )
                )
            )
        return "".join(chunks)

    def _audit_rejected(self, reason: str) -> None:
        self.audit.record(
            event_type="patch.rejected",
            summary=reason,
            subject_type="patch",
            subject_id=None,
            actor_user_id=self.actor_user_id,
            agent_run_id=self.agent_run_id,
        )


def _parse_hunk_header(line: str) -> Hunk:
    match = HUNK_HEADER_PATTERN.match(line)
    if match is None:
        raise PatchRejected(f"invalid hunk header: {line}")
    return Hunk(
        old_start=int(match.group("old_start")),
        old_count=int(match.group("old_count") or "1"),
        new_start=int(match.group("new_start")),
        new_count=int(match.group("new_count") or "1"),
    )


def _require_line(lines: list[str], index: int, expected: str, path: str) -> None:
    if index >= len(lines) or lines[index] != expected:
        raise PatchRejected(f"patch context mismatch in {path}")


def _risk_categories(path: str, added: int, deleted: int) -> set[PatchRiskCategory]:
    lower = path.lower()
    name = Path(lower).name
    categories: set[PatchRiskCategory] = set()
    if "auth" in lower or "security" in lower:
        categories.add(PatchRiskCategory.AUTH_SECURITY)
    if lower.startswith(("alembic/versions/", "migrations/")):
        categories.add(PatchRiskCategory.DATABASE_MIGRATION)
    if name in {"pyproject.toml", "package.json"} or name.startswith("requirements"):
        categories.add(PatchRiskCategory.DEPENDENCY_MANIFEST)
    if lower.startswith((".github/workflows/", ".circleci/")) or name in {
        ".gitlab-ci.yml",
        "jenkinsfile",
    }:
        categories.add(PatchRiskCategory.CI_CD_CONFIG)
    if name.startswith("dockerfile") or name in {"docker-compose.yml", "vercel.json", "fly.toml"}:
        categories.add(PatchRiskCategory.DEPLOYMENT_CONFIG)
    if name.startswith(".env") or "secret" in lower or "credentials" in lower or "config" in lower:
        categories.add(PatchRiskCategory.SECRETS_CONFIG)
    if lower.startswith("app/security/") or "policy" in lower or name == "agents.md":
        categories.add(PatchRiskCategory.PERMISSION_POLICY)
    if deleted >= LARGE_DELETION_LINES:
        categories.add(PatchRiskCategory.LARGE_DELETION)
    if name.endswith(".lock") or name in {
        "poetry.lock",
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
    }:
        categories.add(PatchRiskCategory.GENERATED_LOCKFILE)
    return categories


def _human_summary(
    files: list[FileDiffMetadata],
    risk_categories: set[PatchRiskCategory],
) -> str:
    changed = len(files)
    added = sum(file.added_lines for file in files)
    deleted = sum(file.deleted_lines for file in files)
    summary = f"{changed} file(s), +{added}/-{deleted}"
    if risk_categories:
        risks = ", ".join(category.value for category in sorted(risk_categories))
        return f"{summary}; high risk: {risks}"
    return f"{summary}; no high-risk categories detected"
