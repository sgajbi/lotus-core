from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATALOG_PATH = Path("docs/architecture/runtime-boundary-decision-catalog.json")
TEMPLATE_PATH = Path("docs/architecture/templates/runtime-boundary-decision-record-template.md")
STANDARD_PATH = Path("docs/standards/runtime-boundary-decision-standard.md")
PR_TEMPLATE_PATH = Path(".github/pull_request_template.md")
CURRENT_STATE_STATUS = "current-state-revalidation-required"
APPROVED_STATUS = "runtime-split-approved"
VALID_STATUSES = {CURRENT_STATE_STATUS, APPROVED_STATUS, "runtime-split-rejected"}


@dataclass(frozen=True, slots=True)
class RuntimeBoundaryDecisionFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def find_runtime_boundary_decision_findings(
    root: Path,
) -> list[RuntimeBoundaryDecisionFinding]:
    root = root.resolve()
    findings: list[RuntimeBoundaryDecisionFinding] = []
    catalog = _load_catalog(root, findings)
    if catalog is None:
        return findings

    baseline_paths = set(catalog["baselineCurrentStateServicePaths"])
    records = catalog["decisionRecords"]
    records_by_path = {record["servicePath"]: record for record in records}
    discovered_paths = _discover_deployable_service_paths(root)

    for service_path in sorted(discovered_paths):
        record = records_by_path.get(service_path)
        if record is None:
            findings.append(
                RuntimeBoundaryDecisionFinding(
                    path=service_path,
                    rule="missing-runtime-boundary-decision",
                    detail=(
                        "deployable service root has a Dockerfile but no runtime-boundary "
                        "decision catalog entry"
                    ),
                )
            )
            continue
        findings.extend(_validate_record(root=root, record=record, baseline_paths=baseline_paths))

    for service_path in sorted(records_by_path):
        if service_path not in discovered_paths:
            findings.append(
                RuntimeBoundaryDecisionFinding(
                    path=service_path,
                    rule="stale-runtime-boundary-decision",
                    detail="catalog entry has no matching deployable Dockerfile",
                )
            )

    for required_path in (TEMPLATE_PATH, STANDARD_PATH, PR_TEMPLATE_PATH):
        if not (root / required_path).exists():
            findings.append(
                RuntimeBoundaryDecisionFinding(
                    path=required_path.as_posix(),
                    rule="missing-runtime-boundary-governance-file",
                    detail="required runtime-boundary governance file is missing",
                )
            )

    if (root / PR_TEMPLATE_PATH).exists():
        pr_template = (root / PR_TEMPLATE_PATH).read_text(encoding="utf-8")
        if "runtime-boundary decision" not in pr_template.lower():
            findings.append(
                RuntimeBoundaryDecisionFinding(
                    path=PR_TEMPLATE_PATH.as_posix(),
                    rule="missing-pr-runtime-boundary-checklist",
                    detail="PR template must ask for runtime-boundary decision evidence",
                )
            )

    return findings


def _load_catalog(
    root: Path,
    findings: list[RuntimeBoundaryDecisionFinding],
) -> dict[str, Any] | None:
    path = root / CATALOG_PATH
    if not path.exists():
        findings.append(
            RuntimeBoundaryDecisionFinding(
                path=CATALOG_PATH.as_posix(),
                rule="missing-runtime-boundary-catalog",
                detail="runtime-boundary decision catalog is missing",
            )
        )
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    for field_name in (
        "baselineCurrentStateServicePaths",
        "decisionRecords",
    ):
        if not isinstance(payload.get(field_name), list):
            findings.append(
                RuntimeBoundaryDecisionFinding(
                    path=CATALOG_PATH.as_posix(),
                    rule="invalid-runtime-boundary-catalog",
                    detail=f"{field_name} must be a list",
                )
            )
            return None
    return payload


def _discover_deployable_service_paths(root: Path) -> set[str]:
    service_root = root / "src" / "services"
    return {
        dockerfile.parent.relative_to(root).as_posix()
        for dockerfile in service_root.rglob("Dockerfile")
        if dockerfile.is_file()
    }


def _validate_record(
    *,
    root: Path,
    record: dict[str, Any],
    baseline_paths: set[str],
) -> list[RuntimeBoundaryDecisionFinding]:
    findings: list[RuntimeBoundaryDecisionFinding] = []
    service_path = _string_field(record, "servicePath")
    if service_path is None:
        return [
            RuntimeBoundaryDecisionFinding(
                path=CATALOG_PATH.as_posix(),
                rule="invalid-runtime-boundary-record",
                detail="record is missing servicePath",
            )
        ]
    status = _string_field(record, "status")
    if status not in VALID_STATUSES:
        findings.append(
            RuntimeBoundaryDecisionFinding(
                path=service_path,
                rule="invalid-runtime-boundary-status",
                detail=f"status must be one of {sorted(VALID_STATUSES)}",
            )
        )
    if status == CURRENT_STATE_STATUS and service_path not in baseline_paths:
        findings.append(
            RuntimeBoundaryDecisionFinding(
                path=service_path,
                rule="new-service-cannot-use-current-state-status",
                detail="new deployable services require runtime-split-approved decision evidence",
            )
        )
    if status == APPROVED_STATUS and service_path in baseline_paths:
        findings.append(
            RuntimeBoundaryDecisionFinding(
                path=service_path,
                rule="baseline-service-status-mismatch",
                detail=(
                    "baseline current-state services should stay "
                    "revalidation-required until reviewed"
                ),
            )
        )
    for field_name in (
        "serviceId",
        "decisionRecordPath",
        "rationaleSummary",
        "revalidationOwner",
    ):
        if not _string_field(record, field_name):
            findings.append(
                RuntimeBoundaryDecisionFinding(
                    path=service_path,
                    rule="missing-runtime-boundary-field",
                    detail=f"{field_name} must be a non-empty string",
                )
            )
    for field_name in ("inProcessBoundaryEvidence", "runtimeBoundaryDrivers"):
        if not _string_list_field(record, field_name):
            findings.append(
                RuntimeBoundaryDecisionFinding(
                    path=service_path,
                    rule="missing-runtime-boundary-evidence",
                    detail=f"{field_name} must be a non-empty string list",
                )
            )
    decision_record_path = _string_field(record, "decisionRecordPath")
    if decision_record_path and not (root / decision_record_path).exists():
        findings.append(
            RuntimeBoundaryDecisionFinding(
                path=service_path,
                rule="missing-runtime-boundary-decision-record",
                detail=f"decisionRecordPath does not exist: {decision_record_path}",
            )
        )
    return findings


def _string_field(record: dict[str, Any], field_name: str) -> str | None:
    value = record.get(field_name)
    return value if isinstance(value, str) and value.strip() else None


def _string_list_field(record: dict[str, Any], field_name: str) -> list[str] | None:
    value = record.get(field_name)
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return value


def main() -> int:
    findings = find_runtime_boundary_decision_findings(Path.cwd())
    if findings:
        print("Runtime boundary decision guard failed:")
        for finding in findings:
            print(f"  - {finding.as_text()}")
        return 1
    print("Runtime boundary decision guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
