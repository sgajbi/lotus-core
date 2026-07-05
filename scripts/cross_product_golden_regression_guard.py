"""Validate the governed cross-product transaction golden regression pack."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = Path("docs/standards/cross-product-golden-regression-pack.v1.json")
PACK_SCHEMA = "lotus-core.cross-product-golden-regression-pack.v1"
FIXTURE_SCHEMA = "lotus-core.cross-product-transaction-golden-scenarios.v1"


def _load(path: Path) -> dict[str, Any]:
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
    pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)")
    targets: set[str] = set()
    for line in (repo_root / "Makefile").read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match and not line.startswith("\t"):
            targets.add(match.group(1))
    return targets


def _ref_exists(ref: str, *, repo_root: Path, repo_files: set[str], make_targets: set[str]) -> bool:
    normalized = _normalize(ref)
    if normalized.startswith("make "):
        return normalized.removeprefix("make ").split()[0] in make_targets
    return normalized in repo_files or (repo_root / normalized).exists()


def validate_cross_product_golden_pack(
    pack: dict[str, Any],
    fixture: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if pack.get("schema_version") != PACK_SCHEMA:
        findings.append({"invalid_pack_schema_version": pack.get("schema_version")})
    if fixture.get("schema_version") != FIXTURE_SCHEMA:
        findings.append({"invalid_fixture_schema_version": fixture.get("schema_version")})
    if (
        pack.get("owning_repository") != "lotus-core"
        or fixture.get("owning_repository") != "lotus-core"
    ):
        findings.append({"invalid_owning_repository": pack.get("owning_repository")})
    if (
        pack.get("issue") != "sgajbi/lotus-core#607"
        or fixture.get("issue") != "sgajbi/lotus-core#607"
    ):
        findings.append({"invalid_issue": pack.get("issue")})
    if pack.get("guard_command") != "make cross-product-golden-regression-guard":
        findings.append({"invalid_guard_command": pack.get("guard_command")})

    scenarios = fixture.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [*findings, {"missing": "fixture.scenarios"}]

    required_scenarios = set(pack.get("required_scenarios", []))
    actual_scenarios = {str(item.get("id", "")) for item in scenarios if isinstance(item, dict)}
    missing_scenarios = sorted(required_scenarios - actual_scenarios)
    if missing_scenarios:
        findings.append({"missing_scenarios": missing_scenarios})

    allowed_statuses = set(pack.get("allowed_statuses", []))
    required_sections = set(pack.get("required_expected_sections", []))
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            findings.append({"invalid_scenario": scenario})
            continue
        scenario_id = str(scenario.get("id", ""))
        status = scenario.get("status")
        if status not in allowed_statuses:
            findings.append({"scenario": scenario_id, "invalid_status": status})
        expected = scenario.get("expected")
        if not isinstance(expected, dict):
            findings.append({"scenario": scenario_id, "missing": "expected"})
            continue
        missing_sections = sorted(required_sections - set(expected))
        if missing_sections:
            findings.append(
                {"scenario": scenario_id, "missing_expected_sections": missing_sections}
            )
        if status != "implemented" and not scenario.get("gap_links"):
            findings.append({"scenario": scenario_id, "missing": "gap_links"})
        lineage = expected.get("lineage", {})
        if not isinstance(lineage, dict) or not lineage.get("required_fields"):
            findings.append({"scenario": scenario_id, "missing": "lineage.required_fields"})

    repo_files = _repo_files(repo_root)
    make_targets = _make_targets(repo_root)
    missing_refs = [
        ref
        for ref in pack.get("executable_evidence", [])
        if not _ref_exists(
            str(ref), repo_root=repo_root, repo_files=repo_files, make_targets=make_targets
        )
    ]
    if missing_refs:
        findings.append({"missing_executable_evidence": missing_refs})
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=PACK_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = _load(REPO_ROOT / args.pack)
    fixture = _load(REPO_ROOT / pack["fixture"])
    findings = validate_cross_product_golden_pack(pack, fixture, repo_root=REPO_ROOT)
    if findings:
        print("Cross-product golden regression guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Cross-product golden regression guard passed: {args.pack.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
