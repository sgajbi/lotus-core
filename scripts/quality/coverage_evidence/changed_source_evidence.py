"""Parse Git change records into normalized, auditable source-file evidence."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath


class SourceChangeType(StrEnum):
    """Semantic change types emitted by Git name-status output."""

    ADDED = "added"
    COPIED = "copied"
    DELETED = "deleted"
    EXPLICIT = "explicit"
    MODIFIED = "modified"
    RENAMED = "renamed"
    TYPE_CHANGED = "type_changed"
    UNMERGED = "unmerged"
    UNKNOWN = "unknown"


_CHANGE_TYPES = {
    "A": SourceChangeType.ADDED,
    "C": SourceChangeType.COPIED,
    "D": SourceChangeType.DELETED,
    "M": SourceChangeType.MODIFIED,
    "R": SourceChangeType.RENAMED,
    "T": SourceChangeType.TYPE_CHANGED,
    "U": SourceChangeType.UNMERGED,
}


def normalize_repo_path(path: str) -> str:
    """Return one repository-relative path representation on every operating system."""

    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]

    candidate = PurePosixPath(normalized)
    has_windows_drive = bool(candidate.parts and candidate.parts[0].endswith(":"))
    if (
        not normalized
        or normalized == "."
        or candidate.is_absolute()
        or has_windows_drive
        or ".." in candidate.parts
    ):
        raise ValueError(f"Source path must be repository-relative: {path!r}")
    return candidate.as_posix()


@dataclass(frozen=True, slots=True)
class ChangedSourceFile:
    """One Git change with pre-change and post-change source identity."""

    git_status: str
    change_type: SourceChangeType
    current_path: str | None
    previous_path: str | None = None
    similarity_percent: int | None = None

    @property
    def exists_at_head(self) -> bool:
        """Return whether this change identifies a post-change file at ``HEAD``."""

        return self.current_path is not None

    def as_evidence(self) -> dict[str, object]:
        """Serialize stable audit evidence for coverage reports."""

        return {
            "change_type": self.change_type.value,
            "current_path": self.current_path,
            "exists_at_head": self.exists_at_head,
            "git_status": self.git_status,
            "previous_path": self.previous_path,
            "similarity_percent": self.similarity_percent,
        }


def _similarity_percent(status: str) -> int | None:
    suffix = status[1:]
    return int(suffix) if suffix.isdigit() else None


def parse_git_name_status(output: str) -> list[ChangedSourceFile]:
    """Parse ``git diff --name-status -z`` output without losing spaces or rename lineage."""

    tokens = output.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()

    changes: list[ChangedSourceFile] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if not status:
            raise ValueError("Git name-status output contains an empty status token")

        status_code = status[0].upper()
        change_type = _CHANGE_TYPES.get(status_code, SourceChangeType.UNKNOWN)
        path_count = 2 if status_code in {"C", "R"} else 1
        if index + path_count > len(tokens):
            raise ValueError(f"Git name-status record {status!r} is missing a path")

        paths = [normalize_repo_path(path) for path in tokens[index : index + path_count]]
        index += path_count
        if any(not path for path in paths):
            raise ValueError(f"Git name-status record {status!r} contains an empty path")

        if status_code == "D":
            current_path = None
            previous_path = paths[0]
        elif status_code in {"C", "R"}:
            previous_path, current_path = paths
        else:
            current_path = paths[0]
            previous_path = None

        changes.append(
            ChangedSourceFile(
                git_status=status,
                change_type=change_type,
                current_path=current_path,
                previous_path=previous_path,
                similarity_percent=_similarity_percent(status),
            )
        )
    return changes


def read_git_changed_sources(*, repo_root: Path, base_ref: str | None) -> list[ChangedSourceFile]:
    """Read changed sources using merge-base diff first and two-point diff as fallback."""

    if not base_ref:
        return []

    candidates = ([f"{base_ref}...HEAD"], [base_ref, "HEAD"])
    failures: list[str] = []
    for revision_args in candidates:
        completed = subprocess.run(
            [
                "git",
                "diff",
                "--name-status",
                "-z",
                "--find-renames",
                "--find-copies",
                "--find-copies-harder",
                *revision_args,
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode == 0:
            return parse_git_name_status(completed.stdout)
        failures.append(
            f"{' '.join(revision_args)}: {completed.stderr.strip() or 'git diff failed'}"
        )
    raise RuntimeError("Unable to determine changed source evidence; " + "; ".join(failures))


def explicit_changed_sources(paths: list[str], *, repo_root: Path) -> list[ChangedSourceFile]:
    """Represent caller-supplied paths while excluding files absent from the current tree."""

    changes: list[ChangedSourceFile] = []
    for path in paths:
        normalized = normalize_repo_path(path)
        if (repo_root / normalized).is_file():
            current_path = normalized
            previous_path = None
        else:
            current_path = None
            previous_path = normalized
        changes.append(
            ChangedSourceFile(
                git_status="EXPLICIT",
                change_type=SourceChangeType.EXPLICIT,
                current_path=current_path,
                previous_path=previous_path,
            )
        )
    return changes


def coverage_source_target(path: str) -> str:
    """Map a governed source file to an import-safe pytest-cov directory target."""

    normalized = normalize_repo_path(path)
    if not normalized.endswith(".py"):
        raise ValueError(f"Coverage source is not a Python module: {normalized}")

    if normalized.startswith("alembic/"):
        # Coverage.py cannot target one migration file, so the JSON report is
        # subsequently narrowed to the exact changed migration path.
        return "./alembic"

    if not (
        normalized.startswith("src/services/")
        or normalized.startswith("src/libs/portfolio-common/")
    ):
        raise ValueError(f"Coverage source is outside the governed Python trees: {normalized}")

    # Coverage resolves dotted source targets with importlib.find_spec(). Exact
    # module targets can therefore execute side-effectful parent packages before
    # pytest collection. A parent directory is equally precise once JSON output
    # is filtered to the governed changed file, without importing application code.
    return Path(normalized).parent.as_posix()
