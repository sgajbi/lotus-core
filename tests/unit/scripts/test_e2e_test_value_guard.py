from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts.quality import e2e_test_value_guard as guard

FULL_NODE = "tests/e2e/test_example.py::test_full"
SMOKE_NODE = "tests/e2e/test_smoke.py::test_smoke"


def _profile() -> dict[str, Any]:
    return {
        "owner": "lotus-core/example",
        "invariant": "The example capability remains correct across live service boundaries.",
        "production_defect_class": "Cross-service example state diverges.",
        "fixture_boundary": "One isolated example scenario.",
        "external_dependencies": ["PostgreSQL", "Kafka"],
        "source_contracts": ["docs/standards/source.json"],
        "lower_layer_proofs": ["tests/unit/test_example.py"],
        "non_duplication_rationale": (
            "The live workflow proves asynchronous behavior that the referenced lower-layer "
            "contract cannot exercise."
        ),
    }


def _review_evidence() -> dict[str, Any]:
    run_identity = {
        "run_url": "https://github.com/sgajbi/lotus-core/actions/runs/123456789",
        "source_commit": "a" * 40,
        "artifact_sha256": "b" * 64,
    }
    return {
        "ownership_id": "e2e-002",
        "decision": "retain",
        "reviewer": "lotus-core/test-governance",
        "reviewed_at_utc": "2026-07-23T10:00:00Z",
        "rationale": (
            "The live smoke node owns deployed middleware behavior that is not replaced by "
            "the lower-layer contract."
        ),
        "runtime_evidence": {
            "baseline": {**run_identity, "seconds": 1.2},
            "reviewed": {**run_identity, "seconds": 1.1},
        },
        "fault_detection_evidence": {
            **run_identity,
            "fault_id": "correlation-middleware-registration-removed",
            "injection": "Remove the deployed middleware registration.",
            "expected_owning_node": SMOKE_NODE,
            "observed_result": "The exact smoke node failed on the missing correlation header.",
        },
        "impact_assessment": {
            "downstream_impact": "The smoke lane retains its deployed correlation proof.",
            "contract_compatibility": "No production or test contract changes.",
            "replacement_proofs": [],
        },
    }


def _ledger() -> dict[str, Any]:
    return {
        "schema_version": guard.SCHEMA_VERSION,
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#729",
        "guard_command": guard.GUARD_COMMAND,
        "collection": {
            "full_suite": guard.FULL_SUITE,
            "smoke_suite": guard.SMOKE_SUITE,
            "runtime_mode": "live_worker",
            "environment_profile": "e2e",
            "expected_full_node_count": 2,
            "expected_smoke_node_count": 1,
        },
        "closure_policy": {
            "allowed_decisions": sorted(guard.ALLOWED_DECISIONS),
            "blocking_decisions": ["needs-review"],
            "required_non_blocking_evidence": list(guard.REQUIRED_REVIEW_EVIDENCE_FIELD_ORDER),
        },
        "review_evidence": {"review-e2e-002-v1": _review_evidence()},
        "capability_profiles": {"example": _profile()},
        "nodes": [
            {
                "ownership_id": "e2e-001",
                "nodeid": FULL_NODE,
                "capability_profile": "example",
                "current_lanes": [guard.FULL_SUITE],
                "review_decision": "needs-review",
            },
            {
                "ownership_id": "e2e-002",
                "nodeid": SMOKE_NODE,
                "capability_profile": "example",
                "current_lanes": [guard.SMOKE_SUITE, guard.FULL_SUITE],
                "review_decision": "retain",
                "review_evidence_id": "review-e2e-002-v1",
            },
        ],
    }


def _write_repo(tmp_path: Path, ledger: dict[str, Any]) -> Path:
    files = {
        "docs/standards/source.json": "{}\n",
        "tests/unit/test_example.py": "def test_example():\n    pass\n",
        "tests/e2e/test_example.py": "def test_full():\n    pass\n",
        "tests/e2e/test_smoke.py": "def test_smoke():\n    pass\n",
    }
    for relative_path, content in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "lint:\n\t$(MAKE) e2e-test-value-guard\n"
        "e2e-test-value-guard:\n\tpython scripts/quality/e2e_test_value_guard.py\n",
        encoding="utf-8",
    )
    lane_contract_path = tmp_path / guard.LANE_CONTRACT_PATH
    lane_contract_path.write_text(
        json.dumps(
            {
                "e2e_value_governance": {
                    "ledger": guard.LEDGER_PATH.as_posix(),
                    "guard_command": guard.GUARD_COMMAND,
                    "lane_membership_source": "scripts/quality/test_manifest.py",
                    "required_profile_evidence": list(guard.REQUIRED_PROFILE_FIELD_ORDER),
                    "required_review_evidence": list(guard.REQUIRED_REVIEW_EVIDENCE_FIELD_ORDER),
                    "closure_blocking_decisions": ["needs-review"],
                }
            }
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / guard.LEDGER_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return ledger_path


def _evaluate(tmp_path: Path, ledger: dict[str, Any]) -> list[guard.E2ETestValueFinding]:
    return guard.evaluate_e2e_test_value_ledger(
        repo_root=tmp_path,
        ledger_path=_write_repo(tmp_path, ledger),
        full_nodeids=[FULL_NODE, SMOKE_NODE],
        smoke_nodeids=[SMOKE_NODE],
    )


def test_e2e_test_value_guard_accepts_current_repository_inventory() -> None:
    assert guard.evaluate_e2e_test_value_ledger() == []


def test_e2e_test_value_guard_accepts_registered_nodes_and_profiles(
    tmp_path: Path,
) -> None:
    assert _evaluate(tmp_path, _ledger()) == []


def test_e2e_test_value_guard_rejects_missing_and_extra_collected_nodes(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger["nodes"][0]["nodeid"] = "tests/e2e/test_example.py::test_stale"

    findings = _evaluate(tmp_path, ledger)
    rules = {finding.rule for finding in findings}

    assert "collected-node-missing-from-ledger" in rules
    assert "ledger-node-not-collected" in rules


def test_e2e_test_value_guard_rejects_duplicate_ownership_and_node_identity(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    duplicate = deepcopy(ledger["nodes"][0])
    ledger["nodes"].append(duplicate)

    findings = _evaluate(tmp_path, ledger)
    rules = {finding.rule for finding in findings}

    assert "duplicate-ownership-id" in rules
    assert "duplicate-nodeid" in rules


def test_e2e_test_value_guard_rejects_invalid_decision_and_lane_drift(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger["nodes"][1]["review_decision"] = "keep-probably"
    ledger["nodes"][1]["current_lanes"] = [guard.FULL_SUITE]

    findings = _evaluate(tmp_path, ledger)
    rules = {finding.rule for finding in findings}

    assert "invalid-review-decision" in rules
    assert "lane-membership-drift" in rules


def test_e2e_test_value_guard_rejects_missing_evidence_and_weak_rationale(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger["capability_profiles"]["example"]["lower_layer_proofs"] = ["tests/unit/test_missing.py"]
    ledger["capability_profiles"]["example"]["non_duplication_rationale"] = "unique"

    findings = _evaluate(tmp_path, ledger)
    rules = {finding.rule for finding in findings}

    assert "missing-capability-evidence-path" in rules
    assert "weak-non-duplication-rationale" in rules


def test_e2e_test_value_guard_keeps_non_blocking_decision_blocked_without_review_evidence(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger["nodes"][0]["review_decision"] = "retain"

    findings = _evaluate(tmp_path, ledger)

    assert any(finding.rule == "missing-valid-review-evidence" for finding in findings)


def test_e2e_test_value_guard_rejects_incomplete_runtime_fault_and_impact_evidence(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    evidence = ledger["review_evidence"]["review-e2e-002-v1"]
    evidence["runtime_evidence"]["reviewed"]["artifact_sha256"] = "not-a-digest"
    evidence["fault_detection_evidence"]["fault_id"] = ""
    evidence["decision"] = "retire"
    ledger["nodes"][1]["review_decision"] = "retire"

    findings = _evaluate(tmp_path, ledger)
    rules = {finding.rule for finding in findings}

    assert "invalid-runtime-evidence" in rules
    assert "invalid-fault-detection-evidence" in rules
    assert "missing-replacement-proof" in rules
    assert "missing-valid-review-evidence" in rules


def test_e2e_test_value_guard_rejects_uncollectable_replacement_proof_node(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    evidence = ledger["review_evidence"]["review-e2e-002-v1"]
    evidence["decision"] = "replace"
    evidence["impact_assessment"]["replacement_proofs"] = [
        {
            "owning_node": "tests/unit/test_example.py::test_missing_replacement",
            "run_url": "https://github.com/sgajbi/lotus-core/actions/runs/123456789",
            "source_commit": "a" * 40,
            "artifact_sha256": "b" * 64,
        }
    ]
    ledger["nodes"][1]["review_decision"] = "replace"

    findings = _evaluate(tmp_path, ledger)

    assert any(
        finding.rule == "invalid-impact-assessment"
        and finding.detail == "review-e2e-002-v1.replacement_proofs"
        for finding in findings
    )


def test_e2e_test_value_guard_accepts_collectable_replacement_proof_node(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    evidence = ledger["review_evidence"]["review-e2e-002-v1"]
    evidence["decision"] = "replace"
    evidence["impact_assessment"]["replacement_proofs"] = [
        {
            "owning_node": "tests/unit/test_example.py::test_example",
            "run_url": "https://github.com/sgajbi/lotus-core/actions/runs/123456789",
            "source_commit": "a" * 40,
            "artifact_sha256": "b" * 64,
        }
    ]
    ledger["nodes"][1]["review_decision"] = "replace"

    assert _evaluate(tmp_path, ledger) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_url", "https://example.com/unrelated-run"),
        ("run_url", "github-actions:123456"),
        ("run_url", "tests/unit/test_example.py"),
        ("source_commit", "main"),
        ("artifact_sha256", "not-a-digest"),
    ],
)
def test_e2e_test_value_guard_rejects_unbound_fault_run_identity(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    ledger = _ledger()
    ledger["review_evidence"]["review-e2e-002-v1"]["fault_detection_evidence"][field] = value

    findings = _evaluate(tmp_path, ledger)

    assert any(finding.rule == "invalid-fault-detection-evidence" for finding in findings)


def test_e2e_test_value_guard_binds_fault_evidence_to_owning_node(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger["review_evidence"]["review-e2e-002-v1"]["fault_detection_evidence"][
        "expected_owning_node"
    ] = FULL_NODE

    findings = _evaluate(tmp_path, ledger)

    assert any(finding.rule == "fault-evidence-owner-mismatch" for finding in findings)


def test_e2e_test_value_guard_rejects_smoke_nodes_outside_full_inventory(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger_path = _write_repo(tmp_path, ledger)

    findings = guard.evaluate_e2e_test_value_ledger(
        repo_root=tmp_path,
        ledger_path=ledger_path,
        full_nodeids=[FULL_NODE],
        smoke_nodeids=[SMOKE_NODE],
    )

    assert any(finding.rule == "smoke-not-subset-of-full" for finding in findings)


def test_e2e_test_value_guard_rejects_unenforced_make_and_lane_contract(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger_path = _write_repo(tmp_path, ledger)
    (tmp_path / "Makefile").write_text(
        "e2e-test-value-guard:\n\tpython scripts/quality/e2e_test_value_guard.py\n",
        encoding="utf-8",
    )
    (tmp_path / guard.LANE_CONTRACT_PATH).write_text("{}\n", encoding="utf-8")

    findings = guard.evaluate_e2e_test_value_ledger(
        repo_root=tmp_path,
        ledger_path=ledger_path,
        full_nodeids=[FULL_NODE, SMOKE_NODE],
        smoke_nodeids=[SMOKE_NODE],
    )
    rules = {finding.rule for finding in findings}

    assert "guard-not-enforced-by-lint" in rules
    assert "missing-test-lane-e2e-governance" in rules


def test_e2e_test_value_guard_rejects_required_profile_evidence_contract_drift(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    ledger_path = _write_repo(tmp_path, ledger)
    lane_contract_path = tmp_path / guard.LANE_CONTRACT_PATH
    lane_contract = json.loads(lane_contract_path.read_text(encoding="utf-8"))
    lane_contract["e2e_value_governance"]["required_profile_evidence"] = [
        "owner",
        "invariant",
    ]
    lane_contract_path.write_text(json.dumps(lane_contract), encoding="utf-8")

    findings = guard.evaluate_e2e_test_value_ledger(
        repo_root=tmp_path,
        ledger_path=ledger_path,
        full_nodeids=[FULL_NODE, SMOKE_NODE],
        smoke_nodeids=[SMOKE_NODE],
    )

    assert any(
        finding.rule == "test-lane-e2e-governance-drift"
        and "required_profile_evidence" in finding.detail
        for finding in findings
    )


def test_e2e_test_value_guard_writes_deterministic_summary_report(
    tmp_path: Path,
) -> None:
    ledger = _ledger()
    findings = guard.evaluate_e2e_test_value_ledger(
        repo_root=tmp_path,
        ledger_path=_write_repo(tmp_path, ledger),
        full_nodeids=[FULL_NODE, SMOKE_NODE],
        smoke_nodeids=[SMOKE_NODE],
        write_report=True,
    )

    report = json.loads((tmp_path / guard.REPORT_PATH).read_text(encoding="utf-8"))
    assert findings == []
    assert report["full_node_count"] == 2
    assert report["smoke_node_count"] == 1
    assert report["decision_counts"] == {"needs-review": 1, "retain": 1}
    assert report["closure_blocker_count"] == 1
