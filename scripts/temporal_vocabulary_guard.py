"""Guard RFC-0083 temporal vocabulary for public core contracts."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / "docs" / "standards" / "temporal-vocabulary-allowlist.json"

SCANNED_PATHS = (
    REPO_ROOT / "src" / "libs" / "portfolio-common" / "portfolio_common" / "database_models.py",
    REPO_ROOT / "src" / "services" / "ingestion_service" / "app" / "DTOs",
    REPO_ROOT / "src" / "services" / "ingestion_service" / "app" / "routers",
    REPO_ROOT / "src" / "services" / "query_service" / "app" / "dtos",
    REPO_ROOT / "src" / "services" / "query_service" / "app" / "routers",
    REPO_ROOT / "src" / "services" / "query_control_plane_service" / "app" / "contracts",
    REPO_ROOT / "src" / "services" / "query_control_plane_service" / "app" / "routers",
    REPO_ROOT / "src" / "services" / "event_replay_service" / "app" / "routers",
    REPO_ROOT / "src" / "services" / "financial_reconciliation_service" / "app" / "routers",
)

FORBIDDEN_FIELDS = {
    "date": "Use a domain-specific temporal name in public contracts.",
    "timestamp": "Use observed_at, ingested_at, created_at, or updated_at as appropriate.",
    "source_timestamp": "Use observed_at for source-observed time in new contracts.",
}

FIELD_DEFINITION_RE = re.compile(
    r"^(?P<indent>\s{0,8})(?P<field>[A-Za-z_][A-Za-z0-9_]*)\s*(?::|=)\s*"
)


@dataclass(frozen=True)
class FieldOccurrence:
    path: Path
    line_number: int
    field: str
    line: str

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()


def _load_allowlist() -> dict[tuple[str, str], int]:
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    allowlist: dict[tuple[str, str], int] = {}
    for item in payload.get("allowlist", []):
        path = _required_str(item, "path")
        field = _required_str(item, "field")
        expected_count = _required_int(item, "expectedCount")
        allowlist[(path, field)] = expected_count
    return allowlist


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Allowlist item is missing string field {key!r}: {item}")
    return value


def _required_int(item: dict[str, Any], key: str) -> int:
    value = item.get(key)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"Allowlist item is missing non-negative int field {key!r}: {item}")
    return value


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in SCANNED_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return sorted(set(files))


def _iter_forbidden_occurrences() -> list[FieldOccurrence]:
    occurrences: list[FieldOccurrence] = []
    for path in _iter_python_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = FIELD_DEFINITION_RE.match(line)
            if not match:
                continue
            field = match.group("field")
            if field in FORBIDDEN_FIELDS:
                occurrences.append(
                    FieldOccurrence(
                        path=path,
                        line_number=line_number,
                        field=field,
                        line=line.strip(),
                    )
                )
    return occurrences


def _evaluate_occurrences(
    occurrences: list[FieldOccurrence], allowlist: dict[tuple[str, str], int]
) -> list[str]:
    counts = Counter((item.relative_path, item.field) for item in occurrences)
    errors: list[str] = []

    for occurrence in occurrences:
        key = (occurrence.relative_path, occurrence.field)
        if key not in allowlist:
            errors.append(
                f"{occurrence.relative_path}:{occurrence.line_number}: "
                f"forbidden temporal field {occurrence.field!r}. "
                f"{FORBIDDEN_FIELDS[occurrence.field]}"
            )

    for key, expected_count in sorted(allowlist.items()):
        actual_count = counts.get(key, 0)
        if actual_count != expected_count:
            path, field = key
            errors.append(
                f"{path}: field {field!r} occurs {actual_count} times; allowlist "
                f"expects {expected_count}. Update the field to canonical vocabulary "
                "or update the allowlist with owner-slice rationale."
            )

    return errors


def main() -> int:
    allowlist = _load_allowlist()
    occurrences = _iter_forbidden_occurrences()
    errors = _evaluate_occurrences(occurrences, allowlist)

    if errors:
        print("Temporal vocabulary guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Temporal vocabulary guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
