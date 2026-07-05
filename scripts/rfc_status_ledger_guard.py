"""Validate the governed RFC status ledger."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "docs" / "standards" / "rfc-status-ledger.v1.json"

SCHEMA_VERSION = "lotus-core.rfc-status-ledger.v1"
REPOSITORY = "lotus-core"
GUARD_COMMAND = "python scripts/rfc_status_ledger_guard.py"

VALID_STATUSES = {
    "active_current_state",
    "implemented",
    "partially_implemented",
    "target_state",
    "deferred",
    "legacy",
    "superseded",
    "deprecated",
    "archived",
    "historical",
}
REQUIRED_FAMILIES = {"core", "transaction", "architecture", "operations"}
REQUIRED_FIELDS = (
    "rfc_id",
    "title",
    "family",
    "path",
    "status",
    "owner",
    "affected_services",
    "affected_routes",
    "affected_data_models",
    "implementation_refs",
    "test_evidence",
    "docs_links",
    "wiki_links",
    "supported_feature_refs",
    "canonical_registry_refs",
    "supersedes",
    "superseded_by",
    "deprecation_relationship",
    "status_rationale",
)
LIST_FIELDS = {
    "affected_services",
    "affected_routes",
    "affected_data_models",
    "implementation_refs",
    "test_evidence",
    "docs_links",
    "wiki_links",
    "supported_feature_refs",
    "canonical_registry_refs",
    "supersedes",
    "superseded_by",
}
PATH_LIST_FIELDS = {
    "test_evidence",
    "docs_links",
    "wiki_links",
    "supported_feature_refs",
    "canonical_registry_refs",
}
IMPLEMENTED_STATUSES = {"active_current_state", "implemented", "partially_implemented"}
TRANSACTION_REGISTRY = "src/libs/portfolio-common/portfolio_common/transaction_type_registry.py"
SUPPORTED_FEATURES_DOC = "docs/supported-features.md"


@dataclass(frozen=True)
class RfcDocument:
    path: str
    family: str


def _to_repo_path(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def discover_rfc_documents(repo_root: Path = REPO_ROOT) -> list[RfcDocument]:
    documents: list[RfcDocument] = []
    documents.extend(
        RfcDocument(_to_repo_path(path, repo_root), "core")
        for path in sorted((repo_root / "docs" / "RFCs").glob("RFC*.md"))
    )
    transaction_root = repo_root / "docs" / "rfc-transaction-specs"
    if transaction_root.exists():
        documents.extend(
            RfcDocument(_to_repo_path(path, repo_root), "transaction")
            for path in sorted(transaction_root.rglob("*.md"))
        )
    documents.extend(
        RfcDocument(_to_repo_path(path, repo_root), "architecture")
        for path in sorted((repo_root / "docs" / "architecture").glob("RFC-*.md"))
    )
    documents.extend(
        RfcDocument(_to_repo_path(path, repo_root), "operations")
        for path in sorted((repo_root / "docs" / "operations").glob("RFC-*.md"))
    )
    return documents


def load_ledger(path: Path = LEDGER_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_ledger(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"ledger schema_version must be {SCHEMA_VERSION!r}")
    if payload.get("repository") != REPOSITORY:
        errors.append(f"ledger repository must be {REPOSITORY!r}")
    if payload.get("guard_command") != GUARD_COMMAND:
        errors.append(f"ledger guard_command must be {GUARD_COMMAND!r}")

    discovered = discover_rfc_documents(repo_root)
    discovered_by_path = {document.path: document for document in discovered}
    if set(payload.get("families", [])) != REQUIRED_FAMILIES:
        errors.append(
            "ledger families must contain core, transaction, architecture, and operations"
        )

    entries = payload.get("entries")
    if not isinstance(entries, list):
        return errors + ["ledger entries must be a list"]

    entries_by_path: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index} must be an object")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"entry {index} must define non-empty path")
            continue
        if path in entries_by_path:
            errors.append(f"duplicate RFC ledger entry for {path}")
        entries_by_path[path] = entry
        errors.extend(_entry_errors(entry, repo_root=repo_root, discovered=discovered_by_path))

    missing = sorted(set(discovered_by_path) - set(entries_by_path))
    stale = sorted(set(entries_by_path) - set(discovered_by_path))
    if missing:
        errors.append("RFC ledger is missing metadata for: " + ", ".join(missing))
    if stale:
        errors.append("RFC ledger contains stale metadata for: " + ", ".join(stale))
    return errors


def _entry_errors(
    entry: dict[str, Any], *, repo_root: Path, discovered: dict[str, RfcDocument]
) -> list[str]:
    errors: list[str] = []
    path = entry.get("path")
    prefix = str(path)
    for field_name in REQUIRED_FIELDS:
        if field_name not in entry:
            errors.append(f"{prefix}: missing required field {field_name}")
    for field_name in ("rfc_id", "title", "family", "status", "owner", "status_rationale"):
        value = entry.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}: {field_name} must be a non-empty string")
    for field_name in LIST_FIELDS:
        value = entry.get(field_name)
        if not isinstance(value, list):
            errors.append(f"{prefix}: {field_name} must be a list")
            continue
        if field_name in PATH_LIST_FIELDS:
            for ref in value:
                _validate_repo_path_ref(ref, field_name, prefix, repo_root, errors)

    if Path(str(path)).is_absolute():
        errors.append(f"{prefix}: path must be repo-relative")
    elif not (repo_root / str(path)).exists():
        errors.append(f"{prefix}: path does not exist")

    document = discovered.get(str(path))
    if document is not None and entry.get("family") != document.family:
        errors.append(f"{prefix}: family must be {document.family!r}")
    if entry.get("status") not in VALID_STATUSES:
        errors.append(f"{prefix}: status must be one of {', '.join(sorted(VALID_STATUSES))}")

    status = entry.get("status")
    if status in IMPLEMENTED_STATUSES:
        for field_name in ("implementation_refs", "test_evidence", "docs_links"):
            value = entry.get(field_name)
            if not isinstance(value, list) or not value:
                errors.append(f"{prefix}: {status} entries must define {field_name}")

    if entry.get("family") == "transaction" and "/transactions/" in str(path):
        canonical_refs = entry.get("canonical_registry_refs")
        supported_refs = entry.get("supported_feature_refs")
        if not isinstance(canonical_refs, list) or TRANSACTION_REGISTRY not in canonical_refs:
            errors.append(
                f"{prefix}: transaction specs must link the canonical transaction registry"
            )
        if not isinstance(supported_refs, list) or SUPPORTED_FEATURES_DOC not in supported_refs:
            errors.append(f"{prefix}: transaction specs must link supported-feature claims")
    return errors


def _validate_repo_path_ref(
    value: object, field_name: str, entry_path: str, repo_root: Path, errors: list[str]
) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{entry_path}: {field_name} contains an invalid path reference {value!r}")
        return
    if Path(value).is_absolute():
        errors.append(f"{entry_path}: {field_name} reference must be repo-relative: {value}")
        return
    if not (repo_root / value).exists():
        errors.append(f"{entry_path}: {field_name} reference does not exist: {value}")


def main() -> int:
    errors = evaluate_ledger(load_ledger())
    if errors:
        print("RFC status ledger guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("RFC status ledger guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
