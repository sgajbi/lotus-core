"""Validate the governed observability contract test pack."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = Path("docs/standards/observability-contract-test-pack.v1.json")
SCHEMA_VERSION = "lotus-core.observability-contract-test-pack.v1"
REQUIRED_SCENARIOS = {
    "runtime_apps_expose_health_version_and_metrics_surfaces",
    "standard_headers_and_route_template_metrics_are_preserved",
    "malformed_trace_headers_are_normalized_to_valid_w3c_context",
    "forbidden_metric_labels_and_unsafe_logs_are_rejected",
    "diagnostics_and_payload_evidence_remain_source_safe",
}
REQUIRED_CONTRACT_ASSERTIONS = {
    "correlation_request_trace_headers",
}
ALLOWED_STATUSES = {"implemented", "implemented_with_gaps"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _repo_files(repo_root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode == 0:
        return {_normalize(line) for line in completed.stdout.splitlines() if line.strip()}
    return {
        path.relative_to(repo_root).as_posix()
        for path in repo_root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


def _make_targets(repo_root: Path) -> set[str]:
    targets: set[str] = set()
    target_pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)")
    for line in (repo_root / "Makefile").read_text(encoding="utf-8").splitlines():
        match = target_pattern.match(line)
        if match and not line.startswith("\t"):
            targets.add(match.group(1))
    return targets


def _ref_exists(ref: str, *, repo_root: Path, repo_files: set[str]) -> bool:
    normalized = _normalize(ref)
    return normalized in repo_files or (repo_root / normalized).exists()


def _evidence_text(
    scenario: dict[str, Any],
    *,
    repo_root: Path,
) -> str:
    evidence_paths = [repo_root / _normalize(str(ref)) for ref in scenario.get("evidence", [])]
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in evidence_paths
        if path.exists()
    )


def validate_observability_contract_test_pack(
    pack: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        findings.append({"invalid_schema_version": pack.get("schema_version")})
    if pack.get("owning_repository") != "lotus-core":
        findings.append({"invalid_owning_repository": pack.get("owning_repository")})
    if pack.get("issue") != "sgajbi/lotus-core#571":
        findings.append({"invalid_issue": pack.get("issue")})
    if pack.get("guard_command") != "make observability-contract-test-pack-guard":
        findings.append({"invalid_guard_command": pack.get("guard_command")})
    if pack.get("named_ci_lane") != "test-ops-contract":
        findings.append({"invalid_named_ci_lane": pack.get("named_ci_lane")})

    if "observability-contract-test-pack-guard" not in _make_targets(repo_root):
        findings.append({"missing_make_target": "observability-contract-test-pack-guard"})

    scenarios = pack.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [*findings, {"missing": "scenarios"}]

    repo_files = _repo_files(repo_root)
    actual_ids = {str(item.get("id", "")) for item in scenarios if isinstance(item, dict)}
    missing_scenarios = sorted(REQUIRED_SCENARIOS - actual_ids)
    if missing_scenarios:
        findings.append({"missing_scenarios": missing_scenarios})

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            findings.append({"invalid_scenario": scenario})
            continue
        scenario_id = str(scenario.get("id", ""))
        if scenario.get("status") not in ALLOWED_STATUSES:
            findings.append({"scenario": scenario_id, "invalid_status": scenario.get("status")})
        if not scenario.get("observability_family"):
            findings.append({"scenario": scenario_id, "missing": "observability_family"})
        for key in ("evidence", "test_evidence", "contract_assertions"):
            values = scenario.get(key)
            if not isinstance(values, list) or not values:
                findings.append({"scenario": scenario_id, "missing": key})
        assertions = set(str(value) for value in scenario.get("contract_assertions", []))
        missing_assertions = sorted(REQUIRED_CONTRACT_ASSERTIONS - assertions)
        if missing_assertions and "trace" in scenario_id:
            findings.append(
                {"scenario": scenario_id, "missing_contract_assertions": missing_assertions}
            )
        missing_refs = [
            str(ref)
            for ref in scenario.get("evidence", [])
            if not _ref_exists(str(ref), repo_root=repo_root, repo_files=repo_files)
        ]
        if missing_refs:
            findings.append({"scenario": scenario_id, "missing_evidence_refs": missing_refs})
        evidence_text = _evidence_text(scenario, repo_root=repo_root)
        missing_tests = [
            str(name)
            for name in scenario.get("test_evidence", [])
            if str(name) not in evidence_text
        ]
        if missing_tests:
            findings.append({"scenario": scenario_id, "missing_test_evidence": missing_tests})
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=PACK_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = validate_observability_contract_test_pack(
        _load_json(REPO_ROOT / args.pack),
        repo_root=REPO_ROOT,
    )
    if findings:
        print("Observability contract test pack guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Observability contract test pack guard passed: {args.pack.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
