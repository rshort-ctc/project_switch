import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitHistoryEntry:
    commit: str
    subject: str
    file_paths: list[str]


def current_commit(repo_path: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def tracked_and_untracked_files(repo_path: Path) -> set[str] | None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "ls-files", "-co", "--exclude-standard"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return {line for line in result.stdout.splitlines() if line}


def recent_history(repo_path: Path, *, limit: int = 50) -> list[GitHistoryEntry]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            f"--max-count={limit}",
            "--name-only",
            "--format=%H%x09%s",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
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
