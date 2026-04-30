"""Application service package."""

from typing import Any

__all__ = ["AuditService", "RunService", "ToolCallService"]


def __getattr__(name: str) -> Any:
    if name == "AuditService":
        from app.services.audit import AuditService  # noqa: PLC0415

        return AuditService
    if name == "RunService":
        from app.services.runs import RunService  # noqa: PLC0415

        return RunService
    if name == "ToolCallService":
        from app.services.tools import ToolCallService  # noqa: PLC0415

        return ToolCallService
    raise AttributeError(name)
