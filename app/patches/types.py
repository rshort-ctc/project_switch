from enum import StrEnum

from pydantic import BaseModel, Field


class PatchFileStatus(StrEnum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"


class PatchRiskCategory(StrEnum):
    AUTH_SECURITY = "auth_security"
    DATABASE_MIGRATION = "database_migration"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    CI_CD_CONFIG = "ci_cd_config"
    DEPLOYMENT_CONFIG = "deployment_config"
    SECRETS_CONFIG = "secrets_config"
    PERMISSION_POLICY = "permission_policy"
    LARGE_DELETION = "large_deletion"
    GENERATED_LOCKFILE = "generated_lockfile"


class FileDiffMetadata(BaseModel):
    path: str
    old_path: str | None = None
    status: PatchFileStatus
    added_lines: int = 0
    deleted_lines: int = 0
    is_binary: bool = False
    high_risk_categories: list[PatchRiskCategory] = Field(default_factory=list)


class PatchMetadata(BaseModel):
    files: list[FileDiffMetadata] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    added_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    total_added_lines: int = 0
    total_deleted_lines: int = 0
    is_binary: bool = False
    high_risk_categories: list[PatchRiskCategory] = Field(default_factory=list)
    approval_required: bool = False
    human_summary: str = ""


class PatchApplyResult(BaseModel):
    applied: bool
    metadata: PatchMetadata
    rollback_patch: str
    patch_artifact_id: str | None = None
    patch_artifact_path: str | None = None
    rollback_artifact_id: str | None = None
    rollback_artifact_path: str | None = None
