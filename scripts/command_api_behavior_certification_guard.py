"""Validate the governed command API behavior certification pack."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = Path("docs/standards/command-api-behavior-certification-pack.v1.json")
SCHEMA_VERSION = "lotus-core.command-api-behavior-certification-pack.v1"
REQUIRED_SCENARIOS = {
    "valid_command_returns_stable_accepted_response",
    "duplicate_command_returns_replay_safe_response",
    "same_idempotency_key_different_payload_returns_conflict",
    "malformed_payload_returns_structured_validation_error",
    "command_blocked_by_runtime_mode_or_policy_returns_truthful_non_success",
    "dependency_timeout_or_retryable_failure_maps_standard_error_contract",
    "partial_publish_or_bookkeeping_failure_is_not_misleading_success",
    "security_denied_command_uses_standard_problem_contract",
}
REQUIRED_RESPONSE_ASSERTIONS = {
    "http_status",
    "response_schema",
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


def _route_evidence_missing(
    scenario: dict[str, Any],
    *,
    repo_root: Path,
) -> list[str]:
    evidence_paths = [repo_root / _normalize(str(ref)) for ref in scenario.get("evidence", [])]
    evidence_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in evidence_paths
        if path.exists()
    )
    return [
        str(name)
        for name in scenario.get("route_surface_evidence", [])
        if str(name) not in evidence_text
    ]


def validate_command_api_behavior_certification_pack(
    pack: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        findings.append({"invalid_schema_version": pack.get("schema_version")})
    if pack.get("owning_repository") != "lotus-core":
        findings.append({"invalid_owning_repository": pack.get("owning_repository")})
    if pack.get("issue") != "sgajbi/lotus-core#605":
        findings.append({"invalid_issue": pack.get("issue")})
    if pack.get("guard_command") != "make command-api-behavior-certification-guard":
        findings.append({"invalid_guard_command": pack.get("guard_command")})
    if pack.get("named_ci_lane") != "test-ops-contract":
        findings.append({"invalid_named_ci_lane": pack.get("named_ci_lane")})

    make_targets = _make_targets(repo_root)
    if "command-api-behavior-certification-guard" not in make_targets:
        findings.append({"missing_make_target": "command-api-behavior-certification-guard"})

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
        if not scenario.get("command_family"):
            findings.append({"scenario": scenario_id, "missing": "command_family"})
        for key in ("evidence", "route_surface_evidence", "response_assertions"):
            values = scenario.get(key)
            if not isinstance(values, list) or not values:
                findings.append({"scenario": scenario_id, "missing": key})
        assertions = set(str(value) for value in scenario.get("response_assertions", []))
        missing_assertions = sorted(REQUIRED_RESPONSE_ASSERTIONS - assertions)
        if missing_assertions:
            findings.append(
                {"scenario": scenario_id, "missing_response_assertions": missing_assertions}
            )
        missing_refs = [
            str(ref)
            for ref in scenario.get("evidence", [])
            if not _ref_exists(str(ref), repo_root=repo_root, repo_files=repo_files)
        ]
        if missing_refs:
            findings.append({"scenario": scenario_id, "missing_evidence_refs": missing_refs})
        missing_route_evidence = _route_evidence_missing(scenario, repo_root=repo_root)
        if missing_route_evidence:
            findings.append(
                {"scenario": scenario_id, "missing_route_surface_evidence": missing_route_evidence}
            )
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=PACK_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = validate_command_api_behavior_certification_pack(
        _load_json(REPO_ROOT / args.pack),
        repo_root=REPO_ROOT,
    )
    if findings:
        print("Command API behavior certification guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Command API behavior certification guard passed: {args.pack.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
