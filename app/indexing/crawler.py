import fnmatch
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.indexing.git import tracked_and_untracked_files
from app.indexing.languages import detect_language
from app.indexing.types import FileMetadata
from app.security.redaction import contains_secret

VENDOR_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
BINARY_EXTENSIONS = {
    ".7z",
    ".bin",
    ".dll",
    ".exe",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".zip",
}
SECRET_FILE_PATTERNS = (
    ".gitignore",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*secret*",
    "*credentials*",
)


@dataclass(frozen=True)
class CrawlResult:
    files: list[FileMetadata]
    skipped_ignored_files: int
    skipped_binary_files: int


def crawl_files(repo_path: Path, *, git_commit: str | None) -> CrawlResult:
    repo_path = repo_path.resolve()
    git_files = tracked_and_untracked_files(repo_path)
    candidates = (
        _git_candidates(repo_path, git_files)
        if git_files is not None
        else _walk_candidates(repo_path)
    )
    files: list[FileMetadata] = []
    skipped_ignored = 0
    skipped_binary = 0
    for path in candidates:
        relative_path = path.relative_to(repo_path).as_posix()
        if _is_vendor_path(relative_path) or _is_secret_path(relative_path):
            skipped_ignored += 1
            continue
        if _is_binary_path(path) or _looks_binary(path):
            skipped_binary += 1
            continue
        if _contains_secret(path):
            skipped_ignored += 1
            continue
        stat = path.stat()
        files.append(
            FileMetadata(
                path=path,
                relative_path=relative_path,
                language=detect_language(path),
                sha256=_hash_file(path),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                git_commit=git_commit,
            )
        )
    files.sort(key=lambda item: item.relative_path)
    return CrawlResult(
        files=files, skipped_ignored_files=skipped_ignored, skipped_binary_files=skipped_binary
    )


def _git_candidates(repo_path: Path, git_files: set[str]) -> list[Path]:
    return [repo_path / relative for relative in git_files if (repo_path / relative).is_file()]


def _walk_candidates(repo_path: Path) -> list[Path]:
    ignore_patterns = _read_gitignore(repo_path)
    candidates: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_path).as_posix()
        if any(fnmatch.fnmatch(relative, pattern) for pattern in ignore_patterns):
            continue
        candidates.append(path)
    return candidates


def _read_gitignore(repo_path: Path) -> list[str]:
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        return []
    return [
        line.strip()
        for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _is_vendor_path(relative_path: str) -> bool:
    return any(part in VENDOR_DIRS for part in relative_path.split("/"))


def _is_secret_path(relative_path: str) -> bool:
    name = Path(relative_path).name
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_FILE_PATTERNS)


def _is_binary_path(path: Path) -> bool:
    return path.suffix.lower() in BINARY_EXTENSIONS


def _looks_binary(path: Path) -> bool:
    sample = path.read_bytes()[:2048]
    return b"\0" in sample


def _contains_secret(path: Path) -> bool:
    sample = path.read_text(encoding="utf-8", errors="ignore")[:8192]
    return contains_secret(sample)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
