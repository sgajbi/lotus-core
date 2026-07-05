"""Validate the governed concurrency and duplicate-delivery test pack."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = Path("docs/standards/concurrency-duplicate-delivery-test-pack.v1.json")
SCHEMA_VERSION = "lotus-core.concurrency-duplicate-delivery-test-pack.v1"
REQUIRED_SCENARIOS = {
    "same_idempotency_key_concurrent_submit",
    "same_semantic_event_different_transport_offsets",
    "concurrent_price_update_same_instrument_window",
    "concurrent_transaction_update_same_lot_window",
    "valuation_aggregation_claim_race_and_stale_lease_reset",
    "outbox_dispatch_success_failure_split",
    "replay_and_live_consumer_same_business_event",
    "cancellation_correction_during_recalculation",
}
ALLOWED_STATUSES = {"implemented", "representative_implemented"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def _make_targets(repo_root: Path) -> set[str]:
    targets: set[str] = set()
    target_pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)")
    for line in (repo_root / "Makefile").read_text(encoding="utf-8").splitlines():
        match = target_pattern.match(line)
        if match and not line.startswith("\t"):
            targets.add(match.group(1))
    return targets


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


def _ref_exists(ref: str, *, repo_root: Path, repo_files: set[str], make_targets: set[str]) -> bool:
    normalized = _normalize(ref)
    if normalized.startswith("make "):
        return normalized.removeprefix("make ").split()[0] in make_targets
    return normalized in repo_files or (repo_root / normalized).exists()


def validate_concurrency_duplicate_delivery_pack(
    pack: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        findings.append({"invalid_schema_version": pack.get("schema_version")})
    if pack.get("owning_repository") != "lotus-core":
        findings.append({"invalid_owning_repository": pack.get("owning_repository")})
    if pack.get("issue") != "sgajbi/lotus-core#608":
        findings.append({"invalid_issue": pack.get("issue")})
    if pack.get("guard_command") != "make concurrency-duplicate-delivery-guard":
        findings.append({"invalid_guard_command": pack.get("guard_command")})

    scenarios = pack.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [*findings, {"missing": "scenarios"}]

    repo_files = _repo_files(repo_root)
    make_targets = _make_targets(repo_root)
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
        for key in ("evidence", "deterministic_primitives", "state_assertions"):
            values = scenario.get(key)
            if not isinstance(values, list) or not values:
                findings.append({"scenario": scenario_id, "missing": key})
        missing_refs = [
            str(ref)
            for ref in scenario.get("evidence", [])
            if not _ref_exists(
                str(ref),
                repo_root=repo_root,
                repo_files=repo_files,
                make_targets=make_targets,
            )
        ]
        if missing_refs:
            findings.append({"scenario": scenario_id, "missing_evidence_refs": missing_refs})
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=PACK_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = validate_concurrency_duplicate_delivery_pack(
        _load_json(REPO_ROOT / args.pack),
        repo_root=REPO_ROOT,
    )
    if findings:
        print("Concurrency duplicate-delivery guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Concurrency duplicate-delivery guard passed: {args.pack.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
