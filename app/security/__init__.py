"""Security and policy package."""

from typing import Any

__all__ = [
    "ACTION_CLASSIFICATIONS",
    "ActionClass",
    "PermissionLevel",
    "PolicyConfig",
    "PolicyEngine",
    "PolicyEvaluation",
    "PolicyOperation",
    "PolicyRequest",
    "PolicyViolation",
    "classify_action",
    "normalize_action_name",
]


def __getattr__(name: str) -> Any:
    if name in {
        "ACTION_CLASSIFICATIONS",
        "ActionClass",
        "classify_action",
        "normalize_action_name",
    }:
        from app.security import action_policy  # noqa: PLC0415

        return getattr(action_policy, name)
    if name in __all__:
        from app.security import policy  # noqa: PLC0415

        return getattr(policy, name)
    raise AttributeError(name)
