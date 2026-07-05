"""Validate test marker, lane, determinism, and quarantine governance."""

from __future__ import annotations

import json
import re
import sys
import tomllib
import importlib.util
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "standards" / "test-lane-governance.v1.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
SCHEMA_VERSION = "test-lane-governance.v1"
GUARD_COMMAND = "make test-lane-governance-guard"
ISSUE_RE = re.compile(r"^sgajbi/lotus-core#\d+$")


@dataclass(frozen=True, slots=True)
class TestLaneGovernanceFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def evaluate_test_lane_governance(
    *,
    repo_root: Path = REPO_ROOT,
    contract_path: Path | None = None,
    write_report: bool = True,
) -> list[TestLaneGovernanceFinding]:
    repo_root = repo_root.resolve()
    contract_path = contract_path or repo_root / CONTRACT_PATH.relative_to(REPO_ROOT)
    if not contract_path.exists():
        return [
            TestLaneGovernanceFinding(
                path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-test-lane-contract",
                detail="test lane governance contract is missing",
            )
        ]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    findings = _validate_contract(contract, repo_root=repo_root)
    findings.extend(_validate_pytest_markers(contract, repo_root=repo_root))
    findings.extend(_validate_manifest_lanes(contract, repo_root=repo_root))
    findings.extend(_validate_quarantine(contract))
    if write_report:
        _write_flake_report(contract, repo_root=repo_root, findings=findings)
    return findings


def _validate_contract(
    contract: dict[str, Any],
    *,
    repo_root: Path,
) -> list[TestLaneGovernanceFinding]:
    findings: list[TestLaneGovernanceFinding] = []
    contract_rel = CONTRACT_PATH.relative_to(REPO_ROOT).as_posix()
    if contract.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            TestLaneGovernanceFinding(
                path=contract_rel,
                rule="invalid-schema-version",
                detail=f"expected {SCHEMA_VERSION}",
            )
        )
    if contract.get("owning_repository") != "lotus-core":
        findings.append(
            TestLaneGovernanceFinding(
                path=contract_rel,
                rule="invalid-owning-repository",
                detail="owning_repository must be lotus-core",
            )
        )
    if contract.get("guard_command") != GUARD_COMMAND:
        findings.append(
            TestLaneGovernanceFinding(
                path=contract_rel,
                rule="invalid-guard-command",
                detail=f"guard_command must be {GUARD_COMMAND}",
            )
        )
    for field in ("marker_taxonomy", "determinism_policy", "sleep_and_polling_policy"):
        if not isinstance(contract.get(field), dict) or not contract[field]:
            findings.append(
                TestLaneGovernanceFinding(
                    path=contract_rel,
                    rule="missing-policy-section",
                    detail=field,
                )
            )
    _validate_lane_entries(contract, repo_root=repo_root, findings=findings)
    return findings


def _validate_lane_entries(
    contract: dict[str, Any],
    *,
    repo_root: Path,
    findings: list[TestLaneGovernanceFinding],
) -> None:
    lanes = contract.get("ci_lane_mapping")
    if not isinstance(lanes, list) or not lanes:
        findings.append(
            TestLaneGovernanceFinding(
                path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-ci-lane-mapping",
                detail="ci_lane_mapping must be a non-empty list",
            )
        )
        return
    makefile_text = (repo_root / "Makefile").read_text(encoding="utf-8")
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        suite = lane.get("suite")
        make_target = lane.get("make_target")
        if not isinstance(suite, str) or not suite:
            findings.append(
                TestLaneGovernanceFinding(
                    path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="invalid-lane-suite",
                    detail=str(suite),
                )
            )
        if not isinstance(make_target, str) or not make_target.startswith("make "):
            findings.append(
                TestLaneGovernanceFinding(
                    path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="invalid-lane-make-target",
                    detail=str(make_target),
                )
            )
            continue
        target = make_target.removeprefix("make ").strip()
        if f"{target}:" not in makefile_text:
            findings.append(
                TestLaneGovernanceFinding(
                    path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="lane-make-target-missing",
                    detail=make_target,
                )
            )
        for marker_field in ("allowed_markers", "forbidden_markers"):
            markers = lane.get(marker_field)
            if not isinstance(markers, list) or not all(isinstance(item, str) for item in markers):
                findings.append(
                    TestLaneGovernanceFinding(
                        path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                        rule="invalid-lane-marker-list",
                        detail=f"{suite}.{marker_field}",
                    )
                )


def _validate_pytest_markers(
    contract: dict[str, Any],
    *,
    repo_root: Path,
) -> list[TestLaneGovernanceFinding]:
    pyproject = tomllib.loads((repo_root / PYPROJECT_PATH.relative_to(REPO_ROOT)).read_text())
    marker_entries = (
        pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    )
    declared = {str(entry).split(":", 1)[0].strip() for entry in marker_entries}
    required = set(contract.get("marker_taxonomy", {}).get("required_pytest_markers", []))
    missing = sorted(required - declared)
    if not missing:
        return []
    return [
        TestLaneGovernanceFinding(
            path=PYPROJECT_PATH.relative_to(REPO_ROOT).as_posix(),
            rule="missing-pytest-marker",
            detail=", ".join(missing),
        )
    ]


def _validate_manifest_lanes(
    contract: dict[str, Any],
    *,
    repo_root: Path,
) -> list[TestLaneGovernanceFinding]:
    test_manifest = _load_test_manifest(repo_root)

    findings: list[TestLaneGovernanceFinding] = []
    lanes = {lane["suite"]: lane for lane in contract.get("ci_lane_mapping", [])}
    for suite, paths in test_manifest.SUITES.items():
        if suite not in test_manifest.SUITE_RUNTIME_MODE:
            findings.append(
                TestLaneGovernanceFinding(
                    path="scripts/test_manifest.py",
                    rule="suite-missing-runtime-mode",
                    detail=suite,
                )
            )
        if suite not in test_manifest.SUITE_ENV_PROFILE:
            findings.append(
                TestLaneGovernanceFinding(
                    path="scripts/test_manifest.py",
                    rule="suite-missing-env-profile",
                    detail=suite,
                )
            )
        lane = lanes.get(suite)
        if lane is None:
            continue
        expected_mode = lane.get("runtime_mode")
        actual_mode = test_manifest.SUITE_RUNTIME_MODE.get(suite)
        if actual_mode != expected_mode:
            findings.append(
                TestLaneGovernanceFinding(
                    path="scripts/test_manifest.py",
                    rule="suite-runtime-mode-drift",
                    detail=f"{suite}: contract={expected_mode} manifest={actual_mode}",
                )
            )
        expected_profile = lane.get("environment_profile")
        actual_profile = test_manifest.SUITE_ENV_PROFILE.get(suite)
        if actual_profile != expected_profile:
            findings.append(
                TestLaneGovernanceFinding(
                    path="scripts/test_manifest.py",
                    rule="suite-environment-profile-drift",
                    detail=f"{suite}: contract={expected_profile} manifest={actual_profile}",
                )
            )
        findings.extend(_validate_suite_paths(suite, paths, actual_mode))
    unit_args = " ".join(test_manifest.SUITE_PYTEST_ARGS.get("unit", []))
    for forbidden in ("integration_db", "db_direct", "live_worker", "e2e"):
        if forbidden not in unit_args:
            findings.append(
                TestLaneGovernanceFinding(
                    path="scripts/test_manifest.py",
                    rule="unit-suite-missing-runtime-exclusion",
                    detail=forbidden,
                )
            )
    return findings


def _load_test_manifest(repo_root: Path) -> Any:
    manifest_path = repo_root / "scripts" / "test_manifest.py"
    module_name = f"_lotus_core_test_manifest_{abs(hash(manifest_path))}"
    spec = importlib.util.spec_from_file_location(module_name, manifest_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load test manifest from {manifest_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _validate_suite_paths(
    suite: str,
    paths: list[str],
    runtime_mode: str | None,
) -> list[TestLaneGovernanceFinding]:
    findings: list[TestLaneGovernanceFinding] = []
    normalized_paths = [path.replace("\\", "/") for path in paths if not path.startswith("-")]
    if runtime_mode == "unit":
        forbidden = [
            path
            for path in normalized_paths
            if path.startswith("tests/integration/") or path.startswith("tests/e2e/")
        ]
        if forbidden:
            findings.append(
                TestLaneGovernanceFinding(
                    path="scripts/test_manifest.py",
                    rule="unit-suite-contains-runtime-test-path",
                    detail=f"{suite}: {', '.join(forbidden)}",
                )
            )
    if runtime_mode == "live_worker":
        non_e2e = [
            path
            for path in normalized_paths
            if path != "tests/e2e" and not path.startswith("tests/e2e/")
        ]
        if non_e2e:
            findings.append(
                TestLaneGovernanceFinding(
                    path="scripts/test_manifest.py",
                    rule="live-worker-suite-contains-non-e2e-path",
                    detail=f"{suite}: {', '.join(non_e2e)}",
                )
            )
    return findings


def _validate_quarantine(contract: dict[str, Any]) -> list[TestLaneGovernanceFinding]:
    findings: list[TestLaneGovernanceFinding] = []
    policy = contract.get("quarantine_policy", {})
    required = set(policy.get("required_fields", []))
    maximum_days = int(policy.get("maximum_days", 0))
    today = date.today()
    for entry in policy.get("quarantined_tests", []):
        missing = sorted(field for field in required if not entry.get(field))
        nodeid = str(entry.get("nodeid", "<missing-nodeid>"))
        if missing:
            findings.append(
                TestLaneGovernanceFinding(
                    path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="quarantine-entry-missing-fields",
                    detail=f"{nodeid}: {', '.join(missing)}",
                )
            )
        issue = str(entry.get("issue", ""))
        if issue and not ISSUE_RE.match(issue):
            findings.append(
                TestLaneGovernanceFinding(
                    path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="quarantine-entry-invalid-issue",
                    detail=f"{nodeid}: {issue}",
                )
            )
        quarantined_at = _parse_date(entry.get("quarantined_at"))
        expires_at = _parse_date(entry.get("expires_at"))
        if expires_at and expires_at < today:
            findings.append(
                TestLaneGovernanceFinding(
                    path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="quarantine-entry-expired",
                    detail=nodeid,
                )
            )
        if quarantined_at and expires_at and maximum_days > 0:
            duration = (expires_at - quarantined_at).days
            if duration > maximum_days:
                findings.append(
                    TestLaneGovernanceFinding(
                        path=CONTRACT_PATH.relative_to(REPO_ROOT).as_posix(),
                        rule="quarantine-entry-exceeds-maximum-days",
                        detail=f"{nodeid}: {duration} > {maximum_days}",
                    )
                )
    return findings


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _write_flake_report(
    contract: dict[str, Any],
    *,
    repo_root: Path,
    findings: list[TestLaneGovernanceFinding],
) -> None:
    report_rel = contract.get("flake_tracking_report", {}).get(
        "generated_path",
        "output/test-governance/flake-tracking-report.json",
    )
    report_path = repo_root / str(report_rel)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    quarantined = contract.get("quarantine_policy", {}).get("quarantined_tests", [])
    expired_count = sum(1 for finding in findings if finding.rule == "quarantine-entry-expired")
    report = {
        "schema_version": "flake-tracking-report.v1",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "quarantine_count": len(quarantined),
        "expired_quarantine_count": expired_count,
        "lane_count": len(contract.get("ci_lane_mapping", [])),
        "quarantined_tests": quarantined,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    findings = evaluate_test_lane_governance()
    if findings:
        print("Test lane governance guard failed:")
        for finding in findings:
            print(f"- {finding.as_text()}")
        return 1
    print("Test lane governance guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
