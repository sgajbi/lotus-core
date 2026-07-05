from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path("docs/architecture/architecture-documentation-catalog.v1.json")
ARCHITECTURE_DIR = Path("docs/architecture")
CATALOG_SCHEMA_VERSION = "lotus-core.architecture-documentation-catalog.v1"
CURRENT_STATE_MAP_PATH = Path("docs/architecture/current-state-architecture-map.md")
RUNTIME_BOUNDARY_CATALOG_PATH = Path("docs/architecture/runtime-boundary-decision-catalog.json")

REQUIRED_ENTRY_FIELDS = {
    "path",
    "type",
    "topics",
    "status",
    "owner",
    "freshness_date",
    "related",
    "truth_role",
    "summary",
}
REQUIRED_RULE_FIELDS = {
    "glob",
    "type",
    "status",
    "owner",
    "truth_role",
    "freshness_policy",
}
ALLOWED_TRUTH_ROLES = {
    "current-state-truth",
    "historical-context",
    "review-evidence",
    "template",
    "catalog-metadata",
}
ALLOWED_STATUSES = {"active", "historical", "review-evidence", "superseded"}
CATALOGED_SUFFIXES = {".md", ".json"}
REQUIRED_CURRENT_STATE_MAP_TERMS = (
    "portfolio/account",
    "transaction booking",
    "positions",
    "valuation",
    "cashflow",
    "cost",
    "source-data products",
    "ingestion/replay",
    "reconciliation",
    "operations/supportability",
    "security/audit",
    "platform runtime support",
    "event/outbox flow",
    "database ownership",
    "dependency direction",
    "downstream consumers",
    "prohibited responsibilities",
    "route-contract-family-registry.json",
    "RFC-0082-contract-family-inventory.md",
    "RFC-0083-source-data-product-catalog.md",
    "RFC-0083-eventing-supportability-target-model.md",
    "docs/operations-runbook.md",
    "wiki/API-Surface.md",
    "CODEBASE-REVIEW-LEDGER.md",
    "CR-1330",
    "CR-1331",
)


@dataclass(frozen=True, slots=True)
class ArchitectureCatalogFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def find_architecture_catalog_findings(root: Path = REPO_ROOT) -> list[ArchitectureCatalogFinding]:
    root = root.resolve()
    catalog_path = root / CATALOG_PATH
    if not catalog_path.exists():
        return [
            ArchitectureCatalogFinding(
                CATALOG_PATH.as_posix(),
                "missing-catalog",
                "architecture documentation catalog is missing",
            )
        ]

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    findings: list[ArchitectureCatalogFinding] = []
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        findings.append(
            ArchitectureCatalogFinding(
                CATALOG_PATH.as_posix(),
                "invalid-schema-version",
                f"expected {CATALOG_SCHEMA_VERSION}",
            )
        )

    entries = payload.get("entries", [])
    rules = payload.get("coverage_rules", [])
    _validate_related_navigation(root, payload, findings)
    _validate_entries(root, entries, findings)
    _validate_coverage_rules(root, rules, findings)
    _validate_architecture_coverage(root, entries, rules, findings)
    _validate_truth_role_coverage(payload, findings)
    _validate_index_links(root, findings)
    _validate_current_state_architecture_map(root, entries, findings)
    return findings


def _validate_related_navigation(
    root: Path,
    payload: dict[str, Any],
    findings: list[ArchitectureCatalogFinding],
) -> None:
    required_links = {
        "docs/standards/verified-api-examples.v1.json",
        "docs/standards/rfc-0083-implementation-ledger.json",
        "docs/operations-runbook.md",
        "docs/supported-features.md",
        "wiki/Architecture.md",
        "wiki/API-Surface.md",
        "wiki/Supported-Features.md",
    }
    navigation = payload.get("related_navigation", [])
    missing_links = required_links - set(navigation)
    if missing_links:
        findings.append(
            ArchitectureCatalogFinding(
                CATALOG_PATH.as_posix(),
                "missing-related-navigation",
                ", ".join(sorted(missing_links)),
            )
        )
    for link in navigation:
        if not isinstance(link, str) or not (root / link).exists():
            findings.append(
                ArchitectureCatalogFinding(
                    CATALOG_PATH.as_posix(),
                    "broken-related-navigation",
                    str(link),
                )
            )


def _validate_entries(
    root: Path,
    entries: list[dict[str, Any]],
    findings: list[ArchitectureCatalogFinding],
) -> None:
    seen_paths: set[str] = set()
    for entry in entries:
        entry_path = str(entry.get("path", "<missing-path>"))
        missing_fields = REQUIRED_ENTRY_FIELDS - set(entry)
        if missing_fields:
            findings.append(
                ArchitectureCatalogFinding(
                    entry_path,
                    "missing-entry-fields",
                    ", ".join(sorted(missing_fields)),
                )
            )
        if entry_path in seen_paths:
            findings.append(
                ArchitectureCatalogFinding(entry_path, "duplicate-entry", "path repeated")
            )
        seen_paths.add(entry_path)
        if not (root / entry_path).exists():
            findings.append(
                ArchitectureCatalogFinding(entry_path, "missing-entry-path", "file not found")
            )
        if entry.get("truth_role") not in ALLOWED_TRUTH_ROLES:
            findings.append(
                ArchitectureCatalogFinding(
                    entry_path,
                    "invalid-truth-role",
                    str(entry.get("truth_role")),
                )
            )
        if entry.get("status") not in ALLOWED_STATUSES:
            findings.append(
                ArchitectureCatalogFinding(
                    entry_path,
                    "invalid-status",
                    str(entry.get("status")),
                )
            )
        if not isinstance(entry.get("topics"), list) or not entry.get("topics"):
            findings.append(
                ArchitectureCatalogFinding(
                    entry_path,
                    "missing-topics",
                    "topics must be a non-empty list",
                )
            )
        related = entry.get("related", {})
        for relation_name in ("issues", "rfcs", "prs"):
            if not isinstance(related.get(relation_name), list):
                findings.append(
                    ArchitectureCatalogFinding(
                        entry_path,
                        "invalid-related-shape",
                        f"related.{relation_name} must be a list",
                    )
                )


def _validate_coverage_rules(
    root: Path,
    rules: list[dict[str, Any]],
    findings: list[ArchitectureCatalogFinding],
) -> None:
    for rule in rules:
        rule_id = str(rule.get("glob", "<missing-glob>"))
        missing_fields = REQUIRED_RULE_FIELDS - set(rule)
        if missing_fields:
            findings.append(
                ArchitectureCatalogFinding(
                    rule_id,
                    "missing-coverage-rule-fields",
                    ", ".join(sorted(missing_fields)),
                )
            )
        if rule.get("truth_role") not in ALLOWED_TRUTH_ROLES:
            findings.append(
                ArchitectureCatalogFinding(
                    rule_id,
                    "invalid-rule-truth-role",
                    str(rule.get("truth_role")),
                )
            )
        if rule.get("status") not in ALLOWED_STATUSES:
            findings.append(
                ArchitectureCatalogFinding(
                    rule_id,
                    "invalid-rule-status",
                    str(rule.get("status")),
                )
            )
        if not any(
            fnmatch.fnmatch(path.as_posix(), rule_id) for path in _architecture_document_paths(root)
        ):
            findings.append(
                ArchitectureCatalogFinding(
                    rule_id,
                    "unused-coverage-rule",
                    "no architecture documents match this rule",
                )
            )


def _validate_architecture_coverage(
    root: Path,
    entries: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    findings: list[ArchitectureCatalogFinding],
) -> None:
    explicit_paths = {
        _relative_to_architecture(str(entry.get("path")))
        for entry in entries
        if isinstance(entry.get("path"), str)
    }
    rule_patterns = [str(rule.get("glob")) for rule in rules if isinstance(rule.get("glob"), str)]
    for document_path in _architecture_document_paths(root):
        document = document_path.as_posix()
        if document in explicit_paths:
            continue
        if any(fnmatch.fnmatch(document, pattern) for pattern in rule_patterns):
            continue
        findings.append(
            ArchitectureCatalogFinding(
                f"{ARCHITECTURE_DIR.as_posix()}/{document}",
                "uncataloged-architecture-document",
                "add an explicit catalog entry or an intentional coverage rule",
            )
        )


def _validate_truth_role_coverage(
    payload: dict[str, Any],
    findings: list[ArchitectureCatalogFinding],
) -> None:
    roles = {entry.get("truth_role") for entry in payload.get("entries", [])}
    roles.update(rule.get("truth_role") for rule in payload.get("coverage_rules", []))
    missing_roles = ALLOWED_TRUTH_ROLES - roles
    if missing_roles:
        findings.append(
            ArchitectureCatalogFinding(
                CATALOG_PATH.as_posix(),
                "missing-truth-role-coverage",
                ", ".join(sorted(missing_roles)),
            )
        )


def _validate_index_links(root: Path, findings: list[ArchitectureCatalogFinding]) -> None:
    index_path = root / ARCHITECTURE_DIR / "README.md"
    index_text = index_path.read_text(encoding="utf-8")
    required_terms = (
        "current-state-architecture-map.md",
        "architecture-documentation-catalog.v1.json",
        "current-state truth",
        "review evidence",
        "historical context",
    )
    for term in required_terms:
        if term not in index_text:
            findings.append(
                ArchitectureCatalogFinding(
                    f"{ARCHITECTURE_DIR.as_posix()}/README.md",
                    "index-does-not-use-catalog",
                    term,
                )
            )


def _validate_current_state_architecture_map(
    root: Path,
    entries: list[dict[str, Any]],
    findings: list[ArchitectureCatalogFinding],
) -> None:
    map_path = root / CURRENT_STATE_MAP_PATH
    cataloged_paths = {str(entry.get("path")) for entry in entries}
    if CURRENT_STATE_MAP_PATH.as_posix() not in cataloged_paths:
        findings.append(
            ArchitectureCatalogFinding(
                CURRENT_STATE_MAP_PATH.as_posix(),
                "current-map-not-cataloged",
                "current-state architecture map must be an explicit current-state catalog entry",
            )
        )
    if not map_path.exists():
        findings.append(
            ArchitectureCatalogFinding(
                CURRENT_STATE_MAP_PATH.as_posix(),
                "missing-current-state-map",
                "current-state architecture map is missing",
            )
        )
        return

    map_text = map_path.read_text(encoding="utf-8")
    normalized_map_text = map_text.lower()
    for term in REQUIRED_CURRENT_STATE_MAP_TERMS:
        if term.lower() not in normalized_map_text:
            findings.append(
                ArchitectureCatalogFinding(
                    CURRENT_STATE_MAP_PATH.as_posix(),
                    "current-map-missing-required-anchor",
                    term,
                )
            )

    runtime_catalog_path = root / RUNTIME_BOUNDARY_CATALOG_PATH
    if not runtime_catalog_path.exists():
        findings.append(
            ArchitectureCatalogFinding(
                CURRENT_STATE_MAP_PATH.as_posix(),
                "current-map-missing-runtime-catalog",
                RUNTIME_BOUNDARY_CATALOG_PATH.as_posix(),
            )
        )
        return
    runtime_catalog = json.loads(runtime_catalog_path.read_text(encoding="utf-8"))
    for record in runtime_catalog.get("decisionRecords", []):
        service_id = str(record.get("serviceId", "")).strip()
        service_path = str(record.get("servicePath", "")).strip()
        for required_value in (service_id, service_path):
            if required_value and required_value not in map_text:
                findings.append(
                    ArchitectureCatalogFinding(
                        CURRENT_STATE_MAP_PATH.as_posix(),
                        "current-map-missing-deployable",
                        required_value,
                    )
                )


def _architecture_document_paths(root: Path) -> tuple[Path, ...]:
    architecture_root = root / ARCHITECTURE_DIR
    return tuple(
        sorted(
            path.relative_to(architecture_root)
            for path in architecture_root.rglob("*")
            if path.is_file() and path.suffix in CATALOGED_SUFFIXES
        )
    )


def _relative_to_architecture(path: str) -> str:
    prefix = f"{ARCHITECTURE_DIR.as_posix()}/"
    return path.removeprefix(prefix)


def main() -> int:
    findings = find_architecture_catalog_findings(REPO_ROOT)
    if findings:
        print("Architecture documentation catalog guard failed:")
        for finding in findings:
            print(f"- {finding.as_text()}")
        return 1
    print("Architecture documentation catalog guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
