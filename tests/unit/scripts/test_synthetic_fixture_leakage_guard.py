from __future__ import annotations

import json
from pathlib import Path

from scripts import synthetic_fixture_leakage_guard as guard


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_standard(repo_root: Path) -> dict[str, object]:
    fixture_path = repo_root / "tests/fixtures/private-banking-portfolio-fixture.v1.json"
    _write(
        fixture_path,
        json.dumps(
            {
                "schema_version": "private-banking-portfolio-fixture.v1",
                "fixture_id": "private_banking_portfolio_fixture.v1",
                "synthetic_data": True,
                "safe_for_committed_tests": True,
                "relationships": {key: {} for key in guard.REQUIRED_RELATIONSHIPS},
            }
        ),
    )
    return {
        "schema_version": guard.SCHEMA_VERSION,
        "owning_repository": "lotus-core",
        "guard_command": guard.GUARD_COMMAND,
        "leakage_guard": {
            "scanned_path_globs": [
                "tests/fixtures/**/*",
                "docs/standards/synthetic-test-data-governance.v1.json",
            ],
            "optional_generated_evidence_globs": ["output/**/*.json"],
        },
        "canonical_synthetic_identifiers": [
            {
                "identifier": "CIF_SG_000184",
                "kind": "client_id",
                "synthetic_evidence": "test fixture",
            }
        ],
        "fixture_catalog": [
            {
                "fixture_id": "private_banking_portfolio_fixture.v1",
                "path": "tests/fixtures/private-banking-portfolio-fixture.v1.json",
                "synthetic_data": True,
                "relationship_coverage": sorted(guard.REQUIRED_RELATIONSHIPS),
                "safe_for_committed_tests": True,
            }
        ],
    }


def _write_standard(repo_root: Path, standard: dict[str, object]) -> Path:
    standard_path = repo_root / guard.STANDARD_PATH.relative_to(guard.REPO_ROOT)
    _write(standard_path, json.dumps(standard))
    return standard_path


def test_synthetic_fixture_guard_accepts_current_repo_truth() -> None:
    assert guard.evaluate_synthetic_fixture_governance() == []


def test_synthetic_fixture_guard_accepts_minimal_valid_repo(tmp_path: Path) -> None:
    standard_path = _write_standard(tmp_path, _minimal_standard(tmp_path))

    assert (
        guard.evaluate_synthetic_fixture_governance(
            repo_root=tmp_path,
            standard_path=standard_path,
        )
        == []
    )


def test_synthetic_fixture_guard_rejects_concrete_credentials(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(
        tmp_path / "tests/fixtures/leaky.json",
        '{"headers":{"Authorization":"Bearer abc123456789"},"url":"postgresql://user:secret@db:5432/core"}',
    )

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert {finding.rule for finding in findings} >= {
        "concrete-bearer-token",
        "credentialed-database-url",
    }


def test_synthetic_fixture_guard_rejects_personal_and_account_data(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(
        tmp_path / "tests/fixtures/client.json",
        '{"client_name":"Jane Client","email":"jane.client@example.com","account_number":"12345678"}',
    )

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert {finding.rule for finding in findings} >= {
        "real-looking-client-name",
        "personal-email-address",
        "concrete-account-number",
    }


def test_synthetic_fixture_guard_rejects_uncataloged_cif_identifier(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    standard_path = _write_standard(tmp_path, standard)
    _write(tmp_path / "tests/fixtures/cif.json", '{"client_id":"CIF_SG_999999"}')

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "uncataloged-cif-client-id" for finding in findings)


def test_synthetic_fixture_guard_requires_representative_relationships(tmp_path: Path) -> None:
    standard = _minimal_standard(tmp_path)
    fixture_path = tmp_path / "tests/fixtures/private-banking-portfolio-fixture.v1.json"
    _write(
        fixture_path,
        json.dumps(
            {
                "schema_version": "private-banking-portfolio-fixture.v1",
                "fixture_id": "private_banking_portfolio_fixture.v1",
                "synthetic_data": True,
                "safe_for_committed_tests": True,
                "relationships": {"client": {}, "portfolio": {}},
            }
        ),
    )
    standard_path = _write_standard(tmp_path, standard)

    findings = guard.evaluate_synthetic_fixture_governance(
        repo_root=tmp_path,
        standard_path=standard_path,
    )

    assert any(finding.rule == "missing-representative-relationship" for finding in findings)
