from __future__ import annotations

import json
from pathlib import Path

from scripts.observability_contract_test_pack_guard import (
    REQUIRED_SCENARIOS,
    validate_observability_contract_test_pack,
)


def test_observability_contract_test_pack_matches_current_repo_truth() -> None:
    pack_path = Path("docs/standards/observability-contract-test-pack.v1.json")

    findings = validate_observability_contract_test_pack(
        json.loads(pack_path.read_text(encoding="utf-8")),
        repo_root=Path.cwd(),
    )

    assert findings == []


def test_observability_contract_guard_reports_missing_scenario(tmp_path: Path) -> None:
    pack = {
        "schema_version": "lotus-core.observability-contract-test-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#571",
        "guard_command": "make observability-contract-test-pack-guard",
        "named_ci_lane": "test-ops-contract",
        "scenarios": [
            {
                "id": next(iter(REQUIRED_SCENARIOS)),
                "status": "implemented",
                "observability_family": "health",
                "evidence": ["existing_test.py"],
                "test_evidence": ["test_existing"],
                "contract_assertions": ["correlation_request_trace_headers"],
            }
        ],
    }
    (tmp_path / "Makefile").write_text(
        "observability-contract-test-pack-guard:\n",
        encoding="utf-8",
    )
    (tmp_path / "existing_test.py").write_text("def test_existing(): pass\n", encoding="utf-8")

    findings = validate_observability_contract_test_pack(pack, repo_root=tmp_path)

    assert any("missing_scenarios" in finding for finding in findings)


def test_observability_contract_guard_reports_missing_evidence_ref(tmp_path: Path) -> None:
    pack = {
        "schema_version": "lotus-core.observability-contract-test-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#571",
        "guard_command": "make observability-contract-test-pack-guard",
        "named_ci_lane": "test-ops-contract",
        "scenarios": [
            {
                "id": scenario_id,
                "status": "implemented",
                "observability_family": "health",
                "evidence": ["missing_test.py"],
                "test_evidence": ["test_missing"],
                "contract_assertions": ["correlation_request_trace_headers"],
            }
            for scenario_id in sorted(REQUIRED_SCENARIOS)
        ],
    }
    (tmp_path / "Makefile").write_text(
        "observability-contract-test-pack-guard:\n",
        encoding="utf-8",
    )

    findings = validate_observability_contract_test_pack(pack, repo_root=tmp_path)

    assert any("missing_evidence_refs" in finding for finding in findings)


def test_observability_contract_guard_reports_missing_test_evidence(tmp_path: Path) -> None:
    pack = {
        "schema_version": "lotus-core.observability-contract-test-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#571",
        "guard_command": "make observability-contract-test-pack-guard",
        "named_ci_lane": "test-ops-contract",
        "scenarios": [
            {
                "id": scenario_id,
                "status": "implemented",
                "observability_family": "health",
                "evidence": ["existing_test.py"],
                "test_evidence": ["test_missing"],
                "contract_assertions": ["correlation_request_trace_headers"],
            }
            for scenario_id in sorted(REQUIRED_SCENARIOS)
        ],
    }
    (tmp_path / "Makefile").write_text(
        "observability-contract-test-pack-guard:\n",
        encoding="utf-8",
    )
    (tmp_path / "existing_test.py").write_text("def test_existing(): pass\n", encoding="utf-8")

    findings = validate_observability_contract_test_pack(pack, repo_root=tmp_path)

    assert any("missing_test_evidence" in finding for finding in findings)
