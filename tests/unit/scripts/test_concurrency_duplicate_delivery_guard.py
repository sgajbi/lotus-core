from __future__ import annotations

import json
from pathlib import Path

from scripts.concurrency_duplicate_delivery_guard import (
    REQUIRED_SCENARIOS,
    validate_concurrency_duplicate_delivery_pack,
)


def test_concurrency_duplicate_delivery_pack_matches_current_repo_truth() -> None:
    pack_path = Path("docs/standards/concurrency-duplicate-delivery-test-pack.v1.json")

    findings = validate_concurrency_duplicate_delivery_pack(
        json.loads(pack_path.read_text(encoding="utf-8")),
        repo_root=Path.cwd(),
    )

    assert findings == []


def test_concurrency_duplicate_delivery_guard_reports_missing_scenario(tmp_path: Path) -> None:
    pack = {
        "schema_version": "lotus-core.concurrency-duplicate-delivery-test-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#608",
        "guard_command": "make concurrency-duplicate-delivery-guard",
        "scenarios": [
            {
                "id": next(iter(REQUIRED_SCENARIOS)),
                "status": "implemented",
                "evidence": ["existing_test.py"],
                "deterministic_primitives": ["barrier"],
                "state_assertions": ["one row"],
            }
        ],
    }
    (tmp_path / "Makefile").write_text("concurrency-duplicate-delivery-guard:\n", encoding="utf-8")
    (tmp_path / "existing_test.py").write_text("def test_x(): pass\n", encoding="utf-8")

    findings = validate_concurrency_duplicate_delivery_pack(pack, repo_root=tmp_path)

    assert any("missing_scenarios" in finding for finding in findings)


def test_concurrency_duplicate_delivery_guard_reports_missing_evidence_ref(
    tmp_path: Path,
) -> None:
    pack = {
        "schema_version": "lotus-core.concurrency-duplicate-delivery-test-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#608",
        "guard_command": "make concurrency-duplicate-delivery-guard",
        "scenarios": [
            {
                "id": scenario_id,
                "status": "implemented",
                "evidence": ["missing_test.py"],
                "deterministic_primitives": ["barrier"],
                "state_assertions": ["one row"],
            }
            for scenario_id in sorted(REQUIRED_SCENARIOS)
        ],
    }
    (tmp_path / "Makefile").write_text("concurrency-duplicate-delivery-guard:\n", encoding="utf-8")

    findings = validate_concurrency_duplicate_delivery_pack(pack, repo_root=tmp_path)

    assert any("missing_evidence_refs" in finding for finding in findings)
