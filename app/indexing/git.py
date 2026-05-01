import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitHistoryEntry:
    commit: str
    subject: str
    file_paths: list[str]


def current_commit(repo_path: Path) -> str | None:
    result = _run_git(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
    )
    if result is None:
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def tracked_and_untracked_files(repo_path: Path) -> set[str] | None:
    result = _run_git(
        ["git", "-C", str(repo_path), "ls-files", "-co", "--exclude-standard"],
    )
    if result is None:
        return None
    if result.returncode != 0:
        return None
    return {line for line in result.stdout.splitlines() if line}


def recent_history(repo_path: Path, *, limit: int = 50) -> list[GitHistoryEntry]:
    result = _run_git(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            f"--max-count={limit}",
            "--name-only",
            "--format=%H%x09%s",
        ],
    )
    if result is None:
        return []
    if result.returncode != 0:
        return []

    entries: list[GitHistoryEntry] = []
    commit: str | None = None
    subject = ""
    file_paths: list[str] = []
    for line in result.stdout.splitlines():
        if "\t" in line:
            if commit is not None:
                entries.append(
                    GitHistoryEntry(commit=commit, subject=subject, file_paths=file_paths)
                )
            commit, subject = line.split("\t", 1)
            file_paths = []
            continue
        if line.strip():
            file_paths.append(line.strip())

    if commit is not None:
        entries.append(GitHistoryEntry(commit=commit, subject=subject, file_paths=file_paths))
    return entries


def _run_git(command: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
