"""Safe local patch and diff handling."""

from app.patches.service import PatchRejected, PatchService
from app.patches.types import (
    FileDiffMetadata,
    PatchApplyResult,
    PatchMetadata,
    PatchRiskCategory,
)

__all__ = [
    "FileDiffMetadata",
    "PatchApplyResult",
    "PatchMetadata",
    "PatchRejected",
    "PatchRiskCategory",
    "PatchService",
]
