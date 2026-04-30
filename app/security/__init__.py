"""Security and policy package."""

from typing import Any

__all__ = [
    "PermissionLevel",
    "PolicyConfig",
    "PolicyEngine",
    "PolicyEvaluation",
    "PolicyOperation",
    "PolicyRequest",
    "PolicyViolation",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from app.security import policy  # noqa: PLC0415

        return getattr(policy, name)
    raise AttributeError(name)
