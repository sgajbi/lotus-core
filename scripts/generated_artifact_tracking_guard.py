"""Fail when disposable generated artifacts are tracked as source truth."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TRACKED_PREFIXES = (
    "output/",
    "build/",
    "dist/",
    "htmlcov/",
    "src/services/query_service/build/",
)
FORBIDDEN_TRACKED_PARTS = (
    "/__pycache__/",
    "/build/lib/",
    "/.pytest_cache/",
    "/.ruff_cache/",
    "/.mypy_cache/",
    "/.hypothesis/",
)
FORBIDDEN_TRACKED_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".egg-info",
    ".coverage",
    ".coverage.unit",
    ".coverage.integration_lite",
)


def normalize_tracked_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def is_forbidden_tracked_artifact(path: str) -> bool:
    normalized = normalize_tracked_path(path)
    if not normalized:
        return False
    wrapped = f"/{normalized}/"
    return (
        normalized.startswith(FORBIDDEN_TRACKED_PREFIXES)
        or any(part in wrapped for part in FORBIDDEN_TRACKED_PARTS)
        or normalized.endswith(FORBIDDEN_TRACKED_SUFFIXES)
    )


def find_forbidden_tracked_artifacts(paths: list[str]) -> list[str]:
    return sorted(
        normalized
        for path in paths
        if (normalized := normalize_tracked_path(path))
        and is_forbidden_tracked_artifact(normalized)
    )


def tracked_repository_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def main() -> int:
    findings = find_forbidden_tracked_artifacts(tracked_repository_paths())
    if findings:
        print("Forbidden generated artifacts are tracked:")
        for path in findings:
            print(f"- {path}")
        return 1
    print("Generated artifact tracking guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
