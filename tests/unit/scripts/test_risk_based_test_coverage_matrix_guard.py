from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts import risk_based_test_coverage_matrix_guard as guard


def _minimal_matrix() -> dict[str, object]:
    return {
        "schema_version": "risk-based-test-coverage-matrix.v1",
        "owning_repository": "lotus-core",
        "update_policy": {"gate_command": "make risk-based-test-coverage-matrix-guard"},
        "proof_families": [
            "unit_domain",
            "api",
        ],
        "allowed_gap_statuses": [
            "covered",
            "partial",
        ],
        "required_domains": [
            "transactions",
        ],
        "domains": [
            {
                "id": "transactions",
                "owner": "lotus-core/transaction-lifecycle",
                "risk": "demo",
                "required_proof_families": [
                    "unit_domain",
                    "api",
                ],
                "coverage": [
                    {
                        "proof_family": "unit_domain",
                        "gap_status": "covered",
                        "current_coverage": [
                            "tests/unit/demo/test_transaction_domain.py",
                        ],
                    },
                    {
                        "proof_family": "api",
                        "gap_status": "covered",
                        "current_coverage": [
                            "make openapi-gate",
                        ],
                    },
                ],
            }
        ],
    }


def _write_repo(tmp_path: Path) -> None:
    (tmp_path / "tests/unit/demo").mkdir(parents=True)
    (tmp_path / "tests/unit/demo/test_transaction_domain.py").write_text(
        "def test_demo():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text(
        "openapi-gate:\n\tpython scripts/openapi_quality_gate.py\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.pytest.ini_options]",
                "markers = [",
                '    "api: API contract tests",',
                '    "contract: contract/schema tests",',
                '    "middleware: middleware tests",',
                '    "security: security tests",',
                '    "regression: regression/golden tests",',
                '    "e2e: end-to-end tests",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_current_risk_based_test_coverage_matrix_is_valid() -> None:
    matrix = json.loads((guard.REPO_ROOT / guard.MATRIX_PATH).read_text(encoding="utf-8"))

    assert guard.validate_matrix(matrix) == []


def test_guard_accepts_minimal_valid_matrix(tmp_path: Path) -> None:
    _write_repo(tmp_path)

    assert guard.validate_matrix(_minimal_matrix(), repo_root=tmp_path) == []


def test_guard_requires_all_domain_required_families(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    matrix = _minimal_matrix()
    domain = matrix["domains"][0]
    domain["coverage"] = domain["coverage"][:1]

    findings = guard.validate_matrix(matrix, repo_root=tmp_path)

    assert {"domain": "transactions", "missing_required_families": ["api"]} in findings


def test_guard_rejects_missing_current_coverage_refs(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    matrix = _minimal_matrix()
    domain = matrix["domains"][0]
    domain["coverage"][0]["current_coverage"] = ["tests/unit/missing.py"]

    findings = guard.validate_matrix(matrix, repo_root=tmp_path)

    assert {
        "domain": "transactions",
        "family": "unit_domain",
        "coverage_refs_without_matches": ["tests/unit/missing.py"],
    } in findings


def test_guard_requires_follow_up_for_partial_or_missing_gaps(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    matrix = _minimal_matrix()
    domain = matrix["domains"][0]
    domain["coverage"][0]["gap_status"] = "partial"

    findings = guard.validate_matrix(matrix, repo_root=tmp_path)

    assert {
        "domain": "transactions",
        "family": "unit_domain",
        "missing": "follow_up_issue",
    } in findings


def test_guard_requires_declared_pytest_markers(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    matrix = copy.deepcopy(_minimal_matrix())
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nmarkers = []\n",
        encoding="utf-8",
    )

    findings = guard.validate_matrix(matrix, repo_root=tmp_path)

    assert {
        "missing_pytest_markers": [
            "api",
            "contract",
            "e2e",
            "middleware",
            "regression",
            "security",
        ]
    } in findings
