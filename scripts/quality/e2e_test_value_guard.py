"""Validate end-to-end test ownership, value, and execution-lane truth."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = Path("docs/standards/e2e-test-value-ledger.v1.json")
LANE_CONTRACT_PATH = Path("docs/standards/test-lane-governance.v1.json")
REPORT_PATH = Path("output/test-governance/e2e-test-value-report.json")
SCHEMA_VERSION = "lotus-core.e2e-test-value-ledger.v1"
GUARD_COMMAND = "make e2e-test-value-guard"
FULL_SUITE = "e2e-all"
SMOKE_SUITE = "e2e-smoke"
ALLOWED_DECISIONS = frozenset(
    {
        "retain",
        "rewrite",
        "merge",
        "move-to-lower-layer",
        "replace",
        "retire",
        "needs-review",
    }
)
REQUIRED_PROFILE_FIELD_ORDER = (
    "owner",
    "invariant",
    "production_defect_class",
    "fixture_boundary",
    "external_dependencies",
    "source_contracts",
    "lower_layer_proofs",
    "non_duplication_rationale",
)
REQUIRED_PROFILE_FIELDS = frozenset(REQUIRED_PROFILE_FIELD_ORDER)
OWNERSHIP_ID_PATTERN = re.compile(r"^e2e-\d{3}$")


@dataclass(frozen=True, slots=True)
class E2ETestValueFinding:
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{LEDGER_PATH.as_posix()}: {self.rule}: {self.detail}"


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _collect_nodeids(repo_root: Path, suite: str) -> list[str]:
    command = [
        sys.executable,
        "scripts/quality/test_manifest.py",
        "--suite",
        suite,
        "--collect-only",
        "--quiet",
    ]
    result = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[:2000]
        raise RuntimeError(f"{suite} collection failed ({result.returncode}): {detail}")
    return sorted(
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/e2e/") and "::" in line
    )


def _load_ledger(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ledger root must be an object")
    return value


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_non_empty_string(item) for item in value)
        and len(value) == len(set(value))
    )


def _validate_header(
    ledger: dict[str, Any],
    *,
    repo_root: Path,
) -> list[E2ETestValueFinding]:
    findings: list[E2ETestValueFinding] = []
    expected = {
        "schema_version": SCHEMA_VERSION,
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#729",
        "guard_command": GUARD_COMMAND,
    }
    for field, value in expected.items():
        if ledger.get(field) != value:
            findings.append(
                E2ETestValueFinding(
                    rule=f"invalid-{field.replace('_', '-')}",
                    detail=f"expected {value!r}",
                )
            )
    collection = ledger.get("collection")
    if not isinstance(collection, dict):
        return [
            *findings,
            E2ETestValueFinding(
                rule="missing-collection-policy",
                detail="collection must be an object",
            ),
        ]
    expected_collection = {
        "full_suite": FULL_SUITE,
        "smoke_suite": SMOKE_SUITE,
        "runtime_mode": "live_worker",
        "environment_profile": "e2e",
    }
    for field, value in expected_collection.items():
        if collection.get(field) != value:
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-collection-policy",
                    detail=f"{field} must be {value!r}",
                )
            )
    closure = ledger.get("closure_policy")
    if not isinstance(closure, dict):
        findings.append(
            E2ETestValueFinding(
                rule="missing-closure-policy",
                detail="closure_policy must be an object",
            )
        )
    else:
        allowed = closure.get("allowed_decisions")
        if not isinstance(allowed, list) or set(allowed) != ALLOWED_DECISIONS:
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-allowed-decisions",
                    detail=f"expected {sorted(ALLOWED_DECISIONS)}",
                )
            )
        if closure.get("blocking_decisions") != ["needs-review"]:
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-blocking-decisions",
                    detail="blocking_decisions must be ['needs-review']",
                )
            )
    makefile_path = repo_root / "Makefile"
    makefile = makefile_path.read_text(encoding="utf-8") if makefile_path.is_file() else ""
    if "e2e-test-value-guard:" not in makefile:
        findings.append(
            E2ETestValueFinding(
                rule="missing-make-target",
                detail="e2e-test-value-guard",
            )
        )
    if "\t$(MAKE) e2e-test-value-guard" not in makefile:
        findings.append(
            E2ETestValueFinding(
                rule="guard-not-enforced-by-lint",
                detail="lint must invoke e2e-test-value-guard",
            )
        )
    lane_contract_path = repo_root / LANE_CONTRACT_PATH
    try:
        lane_contract = json.loads(lane_contract_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        findings.append(
            E2ETestValueFinding(
                rule="invalid-test-lane-contract",
                detail=str(exc),
            )
        )
    else:
        governance = lane_contract.get("e2e_value_governance")
        expected_governance = {
            "ledger": LEDGER_PATH.as_posix(),
            "guard_command": GUARD_COMMAND,
            "lane_membership_source": "scripts/quality/test_manifest.py",
            "required_profile_evidence": list(REQUIRED_PROFILE_FIELD_ORDER),
            "closure_blocking_decisions": ["needs-review"],
        }
        if not isinstance(governance, dict):
            findings.append(
                E2ETestValueFinding(
                    rule="missing-test-lane-e2e-governance",
                    detail="e2e_value_governance must be an object",
                )
            )
        else:
            for field, expected_value in expected_governance.items():
                if governance.get(field) != expected_value:
                    findings.append(
                        E2ETestValueFinding(
                            rule="test-lane-e2e-governance-drift",
                            detail=f"{field} must be {expected_value!r}",
                        )
                    )
    return findings


def _validate_profiles(
    ledger: dict[str, Any],
    *,
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], list[E2ETestValueFinding]]:
    raw_profiles = ledger.get("capability_profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        return {}, [
            E2ETestValueFinding(
                rule="missing-capability-profiles",
                detail="capability_profiles must be a non-empty object",
            )
        ]
    profiles: dict[str, dict[str, Any]] = {}
    findings: list[E2ETestValueFinding] = []
    for profile_id, raw_profile in sorted(raw_profiles.items()):
        if not _non_empty_string(profile_id) or not isinstance(raw_profile, dict):
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-capability-profile",
                    detail=str(profile_id),
                )
            )
            continue
        profiles[profile_id] = raw_profile
        missing = sorted(REQUIRED_PROFILE_FIELDS - raw_profile.keys())
        if missing:
            findings.append(
                E2ETestValueFinding(
                    rule="capability-profile-missing-fields",
                    detail=f"{profile_id}: {', '.join(missing)}",
                )
            )
            continue
        for field in (
            "owner",
            "invariant",
            "production_defect_class",
            "fixture_boundary",
            "non_duplication_rationale",
        ):
            if not _non_empty_string(raw_profile.get(field)):
                findings.append(
                    E2ETestValueFinding(
                        rule="invalid-capability-profile-field",
                        detail=f"{profile_id}.{field}",
                    )
                )
        rationale = raw_profile.get("non_duplication_rationale")
        if isinstance(rationale, str) and len(rationale.strip()) < 40:
            findings.append(
                E2ETestValueFinding(
                    rule="weak-non-duplication-rationale",
                    detail=profile_id,
                )
            )
        for field in ("external_dependencies", "source_contracts", "lower_layer_proofs"):
            values = raw_profile.get(field)
            if not _non_empty_string_list(values):
                findings.append(
                    E2ETestValueFinding(
                        rule="invalid-capability-profile-list",
                        detail=f"{profile_id}.{field}",
                    )
                )
                continue
            assert isinstance(values, list)
            if field == "external_dependencies":
                continue
            for relative_path in values:
                if not (repo_root / relative_path).is_file():
                    findings.append(
                        E2ETestValueFinding(
                            rule="missing-capability-evidence-path",
                            detail=f"{profile_id}.{field}: {relative_path}",
                        )
                    )
    return profiles, findings


def _expected_lanes(nodeid: str, smoke_nodeids: set[str]) -> list[str]:
    if nodeid in smoke_nodeids:
        return [SMOKE_SUITE, FULL_SUITE]
    return [FULL_SUITE]


def _validate_nodes(
    ledger: dict[str, Any],
    *,
    profiles: dict[str, dict[str, Any]],
    full_nodeids: Sequence[str],
    smoke_nodeids: Sequence[str],
) -> list[E2ETestValueFinding]:
    findings: list[E2ETestValueFinding] = []
    raw_nodes = ledger.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return [
            E2ETestValueFinding(
                rule="missing-node-inventory",
                detail="nodes must be a non-empty list",
            )
        ]
    full_set, smoke_set = set(full_nodeids), set(smoke_nodeids)
    if not smoke_set <= full_set:
        findings.append(
            E2ETestValueFinding(
                rule="smoke-not-subset-of-full",
                detail=", ".join(sorted(smoke_set - full_set)),
            )
        )
    ledger_nodeids: list[str] = []
    ownership_ids: list[str] = []
    for index, raw_node in enumerate(raw_nodes):
        if not isinstance(raw_node, dict):
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-node-entry",
                    detail=f"index={index}",
                )
            )
            continue
        ownership_id = raw_node.get("ownership_id")
        nodeid = raw_node.get("nodeid")
        profile = raw_node.get("capability_profile")
        decision = raw_node.get("review_decision")
        if not isinstance(ownership_id, str) or not OWNERSHIP_ID_PATTERN.fullmatch(ownership_id):
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-ownership-id",
                    detail=f"index={index}: {ownership_id!r}",
                )
            )
        else:
            ownership_ids.append(ownership_id)
        if (
            not isinstance(nodeid, str)
            or not nodeid.startswith("tests/e2e/")
            or "::" not in nodeid
            or "\\" in nodeid
        ):
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-nodeid",
                    detail=f"index={index}: {nodeid!r}",
                )
            )
            continue
        ledger_nodeids.append(nodeid)
        if profile not in profiles:
            findings.append(
                E2ETestValueFinding(
                    rule="unknown-capability-profile",
                    detail=f"{nodeid}: {profile!r}",
                )
            )
        if decision not in ALLOWED_DECISIONS:
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-review-decision",
                    detail=f"{nodeid}: {decision!r}",
                )
            )
        expected_lanes = _expected_lanes(nodeid, smoke_set)
        if raw_node.get("current_lanes") != expected_lanes:
            findings.append(
                E2ETestValueFinding(
                    rule="lane-membership-drift",
                    detail=(
                        f"{nodeid}: ledger={raw_node.get('current_lanes')!r} "
                        f"collected={expected_lanes!r}"
                    ),
                )
            )
    for value, count in sorted(Counter(ownership_ids).items()):
        if count > 1:
            findings.append(
                E2ETestValueFinding(
                    rule="duplicate-ownership-id",
                    detail=value,
                )
            )
    for value, count in sorted(Counter(ledger_nodeids).items()):
        if count > 1:
            findings.append(
                E2ETestValueFinding(
                    rule="duplicate-nodeid",
                    detail=value,
                )
            )
    missing = sorted(full_set - set(ledger_nodeids))
    extra = sorted(set(ledger_nodeids) - full_set)
    if missing:
        findings.append(
            E2ETestValueFinding(
                rule="collected-node-missing-from-ledger",
                detail=", ".join(missing),
            )
        )
    if extra:
        findings.append(
            E2ETestValueFinding(
                rule="ledger-node-not-collected",
                detail=", ".join(extra),
            )
        )
    if ledger_nodeids != sorted(ledger_nodeids):
        findings.append(
            E2ETestValueFinding(
                rule="node-inventory-not-sorted",
                detail="nodes must be ordered lexically by nodeid",
            )
        )
    collection = ledger.get("collection")
    if isinstance(collection, dict):
        expected_counts = {
            "expected_full_node_count": len(full_set),
            "expected_smoke_node_count": len(smoke_set),
        }
        for field, expected in expected_counts.items():
            if collection.get(field) != expected:
                findings.append(
                    E2ETestValueFinding(
                        rule="collection-count-drift",
                        detail=f"{field}: ledger={collection.get(field)!r} collected={expected}",
                    )
                )
    return findings


def _write_report(
    *,
    repo_root: Path,
    ledger: dict[str, Any],
    full_nodeids: Sequence[str],
    smoke_nodeids: Sequence[str],
    findings: Sequence[E2ETestValueFinding],
) -> None:
    decisions = Counter(
        node.get("review_decision") for node in ledger.get("nodes", []) if isinstance(node, dict)
    )
    report = {
        "schema_version": "lotus-core.e2e-test-value-report.v1",
        "ledger_sha256": _sha256_json(ledger),
        "collected_nodeids_sha256": _sha256_json(sorted(full_nodeids)),
        "full_node_count": len(set(full_nodeids)),
        "smoke_node_count": len(set(smoke_nodeids)),
        "capability_profile_count": len(ledger.get("capability_profiles", {})),
        "decision_counts": dict(sorted(decisions.items(), key=lambda item: str(item[0]))),
        "closure_blocker_count": decisions.get("needs-review", 0),
        "finding_count": len(findings),
    }
    path = repo_root / REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def evaluate_e2e_test_value_ledger(
    *,
    repo_root: Path = REPO_ROOT,
    ledger_path: Path | None = None,
    full_nodeids: Sequence[str] | None = None,
    smoke_nodeids: Sequence[str] | None = None,
    write_report: bool = False,
) -> list[E2ETestValueFinding]:
    repo_root = repo_root.resolve()
    ledger_path = ledger_path or repo_root / LEDGER_PATH
    if not ledger_path.is_file():
        return [
            E2ETestValueFinding(
                rule="missing-ledger",
                detail=LEDGER_PATH.as_posix(),
            )
        ]
    try:
        ledger = _load_ledger(ledger_path)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return [
            E2ETestValueFinding(
                rule="invalid-ledger-json",
                detail=str(exc),
            )
        ]
    try:
        collected_full = (
            list(full_nodeids)
            if full_nodeids is not None
            else _collect_nodeids(repo_root, FULL_SUITE)
        )
        collected_smoke = (
            list(smoke_nodeids)
            if smoke_nodeids is not None
            else _collect_nodeids(repo_root, SMOKE_SUITE)
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return [
            E2ETestValueFinding(
                rule="collection-failed",
                detail=str(exc),
            )
        ]
    findings = _validate_header(ledger, repo_root=repo_root)
    profiles, profile_findings = _validate_profiles(ledger, repo_root=repo_root)
    findings.extend(profile_findings)
    findings.extend(
        _validate_nodes(
            ledger,
            profiles=profiles,
            full_nodeids=collected_full,
            smoke_nodeids=collected_smoke,
        )
    )
    if write_report:
        _write_report(
            repo_root=repo_root,
            ledger=ledger,
            full_nodeids=collected_full,
            smoke_nodeids=collected_smoke,
            findings=findings,
        )
    return findings


def main() -> int:
    findings = evaluate_e2e_test_value_ledger(write_report=True)
    if findings:
        print("E2E test value guard failed:")
        for finding in findings:
            print(f"- {finding.as_text()}")
        return 1
    report = json.loads((REPO_ROOT / REPORT_PATH).read_text(encoding="utf-8"))
    print(
        "E2E test value guard passed: "
        f"full={report['full_node_count']} smoke={report['smoke_node_count']} "
        f"profiles={report['capability_profile_count']} "
        f"closure_blockers={report['closure_blocker_count']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
