"""Validate end-to-end test ownership, value, and execution-lane truth."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
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
REQUIRED_REVIEW_EVIDENCE_FIELD_ORDER = (
    "ownership_id",
    "decision",
    "reviewer",
    "reviewed_at_utc",
    "rationale",
    "runtime_evidence",
    "fault_detection_evidence",
    "impact_assessment",
)
NON_BLOCKING_DECISIONS = ALLOWED_DECISIONS - {"needs-review"}
REPLACEMENT_DECISIONS = frozenset({"merge", "move-to-lower-layer", "replace", "retire"})
OWNERSHIP_ID_PATTERN = re.compile(r"^e2e-\d{3}$")
REVIEW_EVIDENCE_ID_PATTERN = re.compile(r"^review-e2e-\d{3}-v\d+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ACTIONS_RUN_URL_PATTERN = re.compile(
    r"^https://github\.com/sgajbi/lotus-core/actions/runs/\d+(?:/job/\d+)?$"
)


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
        if closure.get("required_non_blocking_evidence") != list(
            REQUIRED_REVIEW_EVIDENCE_FIELD_ORDER
        ):
            findings.append(
                E2ETestValueFinding(
                    rule="invalid-required-review-evidence",
                    detail=(
                        "required_non_blocking_evidence must be "
                        f"{list(REQUIRED_REVIEW_EVIDENCE_FIELD_ORDER)!r}"
                    ),
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
            "required_review_evidence": list(REQUIRED_REVIEW_EVIDENCE_FIELD_ORDER),
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


def _valid_actions_evidence(value: Any, *, require_seconds: bool) -> bool:
    if not isinstance(value, dict):
        return False
    run_url = value.get("run_url")
    source_commit = value.get("source_commit")
    artifact_sha256 = value.get("artifact_sha256")
    if (
        not isinstance(run_url, str)
        or ACTIONS_RUN_URL_PATTERN.fullmatch(run_url) is None
        or not isinstance(source_commit, str)
        or SHA_PATTERN.fullmatch(source_commit) is None
        or not isinstance(artifact_sha256, str)
        or SHA256_PATTERN.fullmatch(artifact_sha256) is None
    ):
        return False
    if not require_seconds:
        return True
    seconds = value.get("seconds")
    return isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0


def _valid_test_nodeid(nodeid: Any, *, repo_root: Path) -> bool:
    if not isinstance(nodeid, str) or "::" not in nodeid or "\\" in nodeid:
        return False
    path = Path(nodeid.split("::", 1)[0])
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.parts[0] == "tests"
        and (repo_root / path).is_file()
    )


def _validate_review_evidence(
    ledger: dict[str, Any],
    *,
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], list[E2ETestValueFinding]]:
    raw_reviews = ledger.get("review_evidence")
    if not isinstance(raw_reviews, dict):
        return {}, [
            E2ETestValueFinding(
                rule="missing-review-evidence-registry",
                detail="review_evidence must be an object",
            )
        ]
    valid_reviews: dict[str, dict[str, Any]] = {}
    findings: list[E2ETestValueFinding] = []
    for review_id, raw_review in sorted(raw_reviews.items()):
        review_findings: list[E2ETestValueFinding] = []

        def reject(rule: str, detail: str) -> None:
            review_findings.append(E2ETestValueFinding(rule=rule, detail=detail))

        if (
            not isinstance(review_id, str)
            or REVIEW_EVIDENCE_ID_PATTERN.fullmatch(review_id) is None
            or not isinstance(raw_review, dict)
        ):
            reject("invalid-review-evidence", str(review_id))
            findings.extend(review_findings)
            continue
        missing = [
            field for field in REQUIRED_REVIEW_EVIDENCE_FIELD_ORDER if field not in raw_review
        ]
        if missing:
            reject("review-evidence-missing-fields", f"{review_id}: {', '.join(missing)}")
            findings.extend(review_findings)
            continue
        ownership_id = raw_review.get("ownership_id")
        decision = raw_review.get("decision")
        if (
            not isinstance(ownership_id, str)
            or OWNERSHIP_ID_PATTERN.fullmatch(ownership_id) is None
        ):
            reject("invalid-review-evidence-ownership", review_id)
        if decision not in NON_BLOCKING_DECISIONS:
            reject("invalid-review-evidence-decision", f"{review_id}: {decision!r}")
        for field in ("reviewer", "rationale"):
            if not _non_empty_string(raw_review.get(field)):
                reject("invalid-review-evidence-field", f"{review_id}.{field}")
        rationale = raw_review.get("rationale")
        if isinstance(rationale, str) and len(rationale.strip()) < 40:
            reject("weak-review-rationale", review_id)
        reviewed_at = raw_review.get("reviewed_at_utc")
        try:
            parsed_reviewed_at = datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))
        except ValueError:
            parsed_reviewed_at = None
        if parsed_reviewed_at is None or parsed_reviewed_at.tzinfo is None:
            reject("invalid-reviewed-at-utc", review_id)

        runtime = raw_review.get("runtime_evidence")
        if not isinstance(runtime, dict):
            reject("invalid-runtime-evidence", review_id)
        else:
            for field in ("baseline", "reviewed"):
                if not _valid_actions_evidence(runtime.get(field), require_seconds=True):
                    reject("invalid-runtime-evidence", f"{review_id}.{field}")

        fault = raw_review.get("fault_detection_evidence")
        if not isinstance(fault, dict):
            reject("invalid-fault-detection-evidence", review_id)
        else:
            for field in ("fault_id", "injection", "observed_result"):
                if not _non_empty_string(fault.get(field)):
                    reject("invalid-fault-detection-evidence", f"{review_id}.{field}")
            if not _valid_test_nodeid(
                fault.get("expected_owning_node"),
                repo_root=repo_root,
            ):
                reject(
                    "invalid-fault-detection-evidence",
                    f"{review_id}.expected_owning_node",
                )
            if not _valid_actions_evidence(fault, require_seconds=False):
                reject("invalid-fault-detection-evidence", f"{review_id}.run_identity")

        impact = raw_review.get("impact_assessment")
        if not isinstance(impact, dict):
            reject("invalid-impact-assessment", review_id)
        else:
            for field in ("downstream_impact", "contract_compatibility"):
                if not _non_empty_string(impact.get(field)):
                    reject("invalid-impact-assessment", f"{review_id}.{field}")
            replacement_proofs = impact.get("replacement_proofs")
            replacement_proofs_valid = isinstance(replacement_proofs, list) and all(
                isinstance(proof, dict)
                and _valid_test_nodeid(proof.get("owning_node"), repo_root=repo_root)
                and _valid_actions_evidence(proof, require_seconds=False)
                for proof in replacement_proofs
            )
            if not replacement_proofs_valid:
                reject("invalid-impact-assessment", f"{review_id}.replacement_proofs")
            if decision in REPLACEMENT_DECISIONS and not replacement_proofs:
                reject("missing-replacement-proof", review_id)
        findings.extend(review_findings)
        if not review_findings:
            valid_reviews[review_id] = raw_review
    return valid_reviews, findings


def _expected_lanes(nodeid: str, smoke_nodeids: set[str]) -> list[str]:
    if nodeid in smoke_nodeids:
        return [SMOKE_SUITE, FULL_SUITE]
    return [FULL_SUITE]


def _validate_nodes(
    ledger: dict[str, Any],
    *,
    profiles: dict[str, dict[str, Any]],
    valid_reviews: dict[str, dict[str, Any]],
    full_nodeids: Sequence[str],
    smoke_nodeids: Sequence[str],
) -> tuple[list[E2ETestValueFinding], int]:
    findings: list[E2ETestValueFinding] = []
    closure_blockers = 0
    raw_nodes = ledger.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return (
            [
                E2ETestValueFinding(
                    rule="missing-node-inventory",
                    detail="nodes must be a non-empty list",
                )
            ],
            1,
        )
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
            closure_blockers += 1
        elif decision == "needs-review":
            closure_blockers += 1
            if "review_evidence_id" in raw_node:
                findings.append(
                    E2ETestValueFinding(
                        rule="premature-review-evidence-reference",
                        detail=nodeid,
                    )
                )
        else:
            review_id = raw_node.get("review_evidence_id")
            review = valid_reviews.get(review_id) if isinstance(review_id, str) else None
            if review is None:
                closure_blockers += 1
                findings.append(
                    E2ETestValueFinding(
                        rule="missing-valid-review-evidence",
                        detail=f"{nodeid}: {review_id!r}",
                    )
                )
            elif review.get("ownership_id") != ownership_id or review.get("decision") != decision:
                closure_blockers += 1
                findings.append(
                    E2ETestValueFinding(
                        rule="review-evidence-node-mismatch",
                        detail=f"{nodeid}: {review_id}",
                    )
                )
            else:
                fault = review.get("fault_detection_evidence")
                if not isinstance(fault, dict) or fault.get("expected_owning_node") != nodeid:
                    closure_blockers += 1
                    findings.append(
                        E2ETestValueFinding(
                            rule="fault-evidence-owner-mismatch",
                            detail=f"{nodeid}: {review_id}",
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
    return findings, closure_blockers


def _write_report(
    *,
    repo_root: Path,
    ledger: dict[str, Any],
    full_nodeids: Sequence[str],
    smoke_nodeids: Sequence[str],
    findings: Sequence[E2ETestValueFinding],
    closure_blocker_count: int,
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
        "closure_blocker_count": closure_blocker_count,
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
    valid_reviews, review_findings = _validate_review_evidence(ledger, repo_root=repo_root)
    findings.extend(review_findings)
    node_findings, closure_blocker_count = _validate_nodes(
        ledger,
        profiles=profiles,
        valid_reviews=valid_reviews,
        full_nodeids=collected_full,
        smoke_nodeids=collected_smoke,
    )
    findings.extend(node_findings)
    if write_report:
        _write_report(
            repo_root=repo_root,
            ledger=ledger,
            full_nodeids=collected_full,
            smoke_nodeids=collected_smoke,
            findings=findings,
            closure_blocker_count=closure_blocker_count,
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
