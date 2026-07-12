import json
from pathlib import Path

from scripts.quality.runtime_boundary_decision_guard import (
    find_runtime_boundary_decision_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _record(
    *,
    service_id: str = "example_service",
    service_path: str = "src/services/example_service",
    status: str = "current-state-revalidation-required",
    decision_record_path: str = "docs/architecture/microservice-boundaries-and-trigger-matrix.md",
    consolidation_target_service_id: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "serviceId": service_id,
        "servicePath": service_path,
        "status": status,
        "decisionRecordPath": decision_record_path,
        "rationaleSummary": "Current-state deployable retained pending revalidation.",
        "inProcessBoundaryEvidence": ["Documented current-state boundary."],
        "runtimeBoundaryDrivers": ["current-state"],
        "revalidationOwner": "lotus-core engineering",
    }
    if consolidation_target_service_id is not None:
        record["consolidationTargetServiceId"] = consolidation_target_service_id
    return record


def _write_required_governance(root: Path) -> None:
    _write(root / "docs/architecture/microservice-boundaries-and-trigger-matrix.md", "# Matrix\n")
    _write(
        root / "docs/architecture/templates/runtime-boundary-decision-record-template.md",
        "# Runtime Boundary Decision Record\n",
    )
    _write(root / "docs/standards/runtime-boundary-decision-standard.md", "# Standard\n")
    _write(
        root / ".github/pull_request_template.md",
        "runtime-boundary decision record checklist\n",
    )


def _write_catalog(
    root: Path,
    *,
    baseline_paths: list[str],
    records: list[dict[str, object]],
) -> None:
    _write(
        root / "docs/architecture/runtime-boundary-decision-catalog.json",
        json.dumps(
            {
                "baselineCurrentStateServicePaths": baseline_paths,
                "decisionRecords": records,
            },
            indent=2,
        ),
    )


def test_runtime_boundary_decision_guard_allows_cataloged_baseline_service(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    _write(tmp_path / "src/services/example_service/Dockerfile", "FROM python:3.13\n")
    _write_catalog(
        tmp_path,
        baseline_paths=["src/services/example_service"],
        records=[_record()],
    )

    assert find_runtime_boundary_decision_findings(tmp_path) == []


def test_runtime_boundary_decision_guard_rejects_missing_catalog_entry(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    _write(tmp_path / "src/services/example_service/Dockerfile", "FROM python:3.13\n")
    _write_catalog(tmp_path, baseline_paths=[], records=[])

    findings = find_runtime_boundary_decision_findings(tmp_path)

    assert [(finding.path, finding.rule) for finding in findings] == [
        ("src/services/example_service", "missing-runtime-boundary-decision")
    ]


def test_runtime_boundary_decision_guard_rejects_stale_catalog_entry(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    _write_catalog(
        tmp_path,
        baseline_paths=["src/services/example_service"],
        records=[_record()],
    )

    findings = find_runtime_boundary_decision_findings(tmp_path)

    assert [(finding.path, finding.rule) for finding in findings] == [
        ("src/services/example_service", "stale-runtime-boundary-decision")
    ]


def test_runtime_boundary_decision_guard_rejects_new_current_state_service(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    _write(tmp_path / "src/services/example_service/Dockerfile", "FROM python:3.13\n")
    _write_catalog(
        tmp_path,
        baseline_paths=[],
        records=[_record()],
    )

    findings = find_runtime_boundary_decision_findings(tmp_path)

    assert any(
        finding.rule == "new-service-cannot-use-current-state-status" for finding in findings
    )


def test_runtime_boundary_decision_guard_rejects_missing_decision_record(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    _write(tmp_path / "src/services/example_service/Dockerfile", "FROM python:3.13\n")
    _write_catalog(
        tmp_path,
        baseline_paths=["src/services/example_service"],
        records=[_record(decision_record_path="docs/architecture/missing-runtime-record.md")],
    )

    findings = find_runtime_boundary_decision_findings(tmp_path)

    assert any(finding.rule == "missing-runtime-boundary-decision-record" for finding in findings)


def test_runtime_boundary_decision_guard_accepts_planned_baseline_consolidation(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    _write(tmp_path / "src/services/example_service/Dockerfile", "FROM python:3.13\n")
    _write_catalog(
        tmp_path,
        baseline_paths=["src/services/example_service"],
        records=[
            _record(
                status="runtime-consolidation-planned",
                consolidation_target_service_id="combined_service",
            )
        ],
    )

    assert find_runtime_boundary_decision_findings(tmp_path) == []


def test_runtime_boundary_decision_guard_rejects_missing_consolidation_target(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    _write(tmp_path / "src/services/example_service/Dockerfile", "FROM python:3.13\n")
    _write_catalog(
        tmp_path,
        baseline_paths=["src/services/example_service"],
        records=[_record(status="runtime-consolidation-planned")],
    )

    findings = find_runtime_boundary_decision_findings(tmp_path)

    assert any(finding.rule == "missing-consolidation-target" for finding in findings)


def test_runtime_boundary_decision_guard_accepts_referenced_consolidation_target(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    legacy_path = "src/services/legacy_service"
    target_path = "src/services/combined_service"
    _write(tmp_path / legacy_path / "Dockerfile", "FROM python:3.13\n")
    _write(tmp_path / target_path / "Dockerfile", "FROM python:3.13\n")
    _write_catalog(
        tmp_path,
        baseline_paths=[legacy_path],
        records=[
            _record(
                service_id="legacy_service",
                service_path=legacy_path,
                status="runtime-consolidation-planned",
                consolidation_target_service_id="combined_service",
            ),
            _record(
                service_id="combined_service",
                service_path=target_path,
                status="runtime-consolidation-target",
            ),
        ],
    )

    assert find_runtime_boundary_decision_findings(tmp_path) == []


def test_runtime_boundary_decision_guard_rejects_unreferenced_consolidation_target(
    tmp_path: Path,
) -> None:
    _write_required_governance(tmp_path)
    target_path = "src/services/combined_service"
    _write(tmp_path / target_path / "Dockerfile", "FROM python:3.13\n")
    _write_catalog(
        tmp_path,
        baseline_paths=[],
        records=[
            _record(
                service_id="combined_service",
                service_path=target_path,
                status="runtime-consolidation-target",
            )
        ],
    )

    findings = find_runtime_boundary_decision_findings(tmp_path)

    assert any(finding.rule == "unreferenced-consolidation-target" for finding in findings)
