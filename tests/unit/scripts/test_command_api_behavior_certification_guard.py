from __future__ import annotations

import json
from pathlib import Path

from scripts.command_api_behavior_certification_guard import (
    REQUIRED_SCENARIOS,
    validate_command_api_behavior_certification_pack,
)


def test_command_api_behavior_certification_pack_matches_current_repo_truth() -> None:
    pack_path = Path("docs/standards/command-api-behavior-certification-pack.v1.json")

    findings = validate_command_api_behavior_certification_pack(
        json.loads(pack_path.read_text(encoding="utf-8")),
        repo_root=Path.cwd(),
    )

    assert findings == []


def test_command_api_behavior_certification_guard_reports_missing_scenario(
    tmp_path: Path,
) -> None:
    pack = {
        "schema_version": "lotus-core.command-api-behavior-certification-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#605",
        "guard_command": "make command-api-behavior-certification-guard",
        "named_ci_lane": "test-ops-contract",
        "scenarios": [
            {
                "id": next(iter(REQUIRED_SCENARIOS)),
                "status": "implemented",
                "command_family": "ingestion",
                "evidence": ["existing_test.py"],
                "route_surface_evidence": ["test_existing"],
                "response_assertions": [
                    "http_status",
                    "response_schema",
                    "operator_reason_code",
                ],
            }
        ],
    }
    (tmp_path / "Makefile").write_text(
        "command-api-behavior-certification-guard:\n",
        encoding="utf-8",
    )
    (tmp_path / "existing_test.py").write_text("def test_existing(): pass\n", encoding="utf-8")

    findings = validate_command_api_behavior_certification_pack(pack, repo_root=tmp_path)

    assert any("missing_scenarios" in finding for finding in findings)


def test_command_api_behavior_certification_guard_reports_missing_evidence_ref(
    tmp_path: Path,
) -> None:
    pack = {
        "schema_version": "lotus-core.command-api-behavior-certification-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#605",
        "guard_command": "make command-api-behavior-certification-guard",
        "named_ci_lane": "test-ops-contract",
        "scenarios": [
            {
                "id": scenario_id,
                "status": "implemented",
                "command_family": "ingestion",
                "evidence": ["missing_test.py"],
                "route_surface_evidence": ["test_missing"],
                "response_assertions": [
                    "http_status",
                    "response_schema",
                    "operator_reason_code",
                ],
            }
            for scenario_id in sorted(REQUIRED_SCENARIOS)
        ],
    }
    (tmp_path / "Makefile").write_text(
        "command-api-behavior-certification-guard:\n",
        encoding="utf-8",
    )

    findings = validate_command_api_behavior_certification_pack(pack, repo_root=tmp_path)

    assert any("missing_evidence_refs" in finding for finding in findings)


def test_command_api_behavior_certification_guard_requires_response_assertions(
    tmp_path: Path,
) -> None:
    pack = {
        "schema_version": "lotus-core.command-api-behavior-certification-pack.v1",
        "owning_repository": "lotus-core",
        "issue": "sgajbi/lotus-core#605",
        "guard_command": "make command-api-behavior-certification-guard",
        "named_ci_lane": "test-ops-contract",
        "scenarios": [
            {
                "id": scenario_id,
                "status": "implemented",
                "command_family": "ingestion",
                "evidence": ["existing_test.py"],
                "route_surface_evidence": ["test_existing"],
                "response_assertions": ["http_status"],
            }
            for scenario_id in sorted(REQUIRED_SCENARIOS)
        ],
    }
    (tmp_path / "Makefile").write_text(
        "command-api-behavior-certification-guard:\n",
        encoding="utf-8",
    )
    (tmp_path / "existing_test.py").write_text("def test_existing(): pass\n", encoding="utf-8")

    findings = validate_command_api_behavior_certification_pack(pack, repo_root=tmp_path)

    assert any("missing_response_assertions" in finding for finding in findings)
