import subprocess
from dataclasses import dataclass
from pathlib import Path

RIPGREP_MATCH_PARTS = 3


@dataclass(frozen=True)
class ExactSearchResult:
    file_path: str
    line_number: int
    line: str


class RipgrepSearcher:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def search(self, query: str, *, limit: int = 20) -> list[ExactSearchResult]:
        try:
            result = subprocess.run(
                [
                    "rg",
                    "--line-number",
                    "--no-heading",
                    "--color",
                    "never",
                    query,
                    str(self.repo_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return []
        if result.returncode not in {0, 1}:
            raise RuntimeError(result.stderr.strip() or "ripgrep search failed")
        matches: list[ExactSearchResult] = []
        for line in result.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) != RIPGREP_MATCH_PARTS:
                continue
            path, line_number, content = parts
            matches.append(
                ExactSearchResult(
                    file_path=Path(path).relative_to(self.repo_path).as_posix(),
                    line_number=int(line_number),
                    line=content,
                )
            )
            if len(matches) >= limit:
                break
        return matches
