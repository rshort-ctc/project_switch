import re

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*(?<![=!<>])=(?!=)\s*['\"]?[^,'\"\s]+"),
    re.compile(r"(?im)^\s*['\"]?(api[_-]?key|token|secret|password)['\"]?\s*:\s*['\"]?[^,'\"\s]+"),
    re.compile(r"(?i)(bearer)\s+[a-z0-9._~+/=-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def redact_secrets(value: str | None) -> str | None:
    if value is None:
        return None

    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(_redaction_replacement, redacted)
    return redacted


def contains_secret(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in SECRET_PATTERNS)


def _redaction_replacement(match: re.Match[str]) -> str:
    if match.lastindex:
        separator = ":" if ":" in match.group(0) and "=" not in match.group(0) else "="
        return f"{match.group(1)}{separator}[REDACTED]"
    return "[REDACTED]"
