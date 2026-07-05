from __future__ import annotations

import json
from pathlib import Path

from scripts import test_lane_governance_guard as guard


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_contract() -> dict[str, object]:
    return {
        "schema_version": guard.SCHEMA_VERSION,
        "owning_repository": "lotus-core",
        "guard_command": guard.GUARD_COMMAND,
        "marker_taxonomy": {
            "required_pytest_markers": ["unit", "integration_db", "db_direct", "live_worker", "e2e"]
        },
        "determinism_policy": {"clock": "fixed"},
        "sleep_and_polling_policy": {"allowed_only_in": ["tests/test_support"]},
        "ci_lane_mapping": [
            {
                "suite": "unit",
                "make_target": "make test",
                "runtime_mode": "unit",
                "environment_profile": "unit",
                "allowed_markers": ["unit"],
                "forbidden_markers": ["integration_db", "db_direct", "live_worker", "e2e"],
            },
            {
                "suite": "e2e-smoke",
                "make_target": "make test-e2e-smoke",
                "runtime_mode": "live_worker",
                "environment_profile": "e2e",
                "allowed_markers": ["live_worker", "e2e"],
                "forbidden_markers": [],
            },
        ],
        "quarantine_policy": {
            "maximum_days": 14,
            "required_fields": [
                "nodeid",
                "owner",
                "issue",
                "reason",
                "quarantined_at",
                "expires_at",
            ],
            "quarantined_tests": [],
        },
        "flake_tracking_report": {
            "generated_path": "output/test-governance/flake-tracking-report.json"
        },
    }


def _write_minimal_repo(repo_root: Path, contract: dict[str, object]) -> Path:
    _write(
        repo_root / "pyproject.toml",
        "\n".join(
            [
                "[tool.pytest.ini_options]",
                "markers = [",
                '  "unit: unit tests",',
                '  "integration_db: database integration tests",',
                '  "db_direct: direct database tests",',
                '  "live_worker: live worker tests",',
                '  "e2e: end-to-end tests",',
                "]",
            ]
        ),
    )
    _write(
        repo_root / "Makefile",
        "test:\n\tpython scripts/test_manifest.py --suite unit\n"
        "test-e2e-smoke:\n\tpython scripts/test_manifest.py --suite e2e-smoke\n",
    )
    _write(
        repo_root / "scripts/test_manifest.py",
        "SUITES = {'unit': ['tests/unit'], 'e2e-smoke': ['tests/e2e/test_smoke.py']}\n"
        "SUITE_RUNTIME_MODE = {'unit': 'unit', 'e2e-smoke': 'live_worker'}\n"
        "SUITE_ENV_PROFILE = {'unit': 'unit', 'e2e-smoke': 'e2e'}\n"
        "SUITE_PYTEST_ARGS = {'unit': ['-m', 'not integration_db and not db_direct and not live_worker and not e2e']}\n",
    )
    _write(repo_root / "scripts/__init__.py", "")
    _write(repo_root / "tests/unit/test_demo.py", "def test_demo():\n    assert True\n")
    _write(repo_root / "tests/e2e/test_smoke.py", "def test_smoke():\n    assert True\n")
    contract_path = repo_root / guard.CONTRACT_PATH.relative_to(guard.REPO_ROOT)
    _write(contract_path, json.dumps(contract))
    return contract_path


def test_test_lane_governance_guard_accepts_current_repo_truth() -> None:
    assert guard.evaluate_test_lane_governance(write_report=False) == []


def test_test_lane_governance_guard_writes_flake_report(tmp_path: Path) -> None:
    contract = _minimal_contract()
    contract_path = _write_minimal_repo(tmp_path, contract)

    assert (
        guard.evaluate_test_lane_governance(
            repo_root=tmp_path,
            contract_path=contract_path,
            write_report=True,
        )
        == []
    )

    report = json.loads(
        (tmp_path / "output/test-governance/flake-tracking-report.json").read_text(encoding="utf-8")
    )
    assert report["quarantine_count"] == 0
    assert report["lane_count"] == 2


def test_test_lane_governance_guard_rejects_missing_marker(tmp_path: Path) -> None:
    contract = _minimal_contract()
    contract_path = _write_minimal_repo(tmp_path, contract)
    _write(
        tmp_path / "pyproject.toml",
        "[tool.pytest.ini_options]\nmarkers = ['unit: unit tests']\n",
    )

    findings = guard.evaluate_test_lane_governance(
        repo_root=tmp_path,
        contract_path=contract_path,
        write_report=False,
    )

    assert any(finding.rule == "missing-pytest-marker" for finding in findings)


def test_test_lane_governance_guard_rejects_unit_lane_runtime_drift(tmp_path: Path) -> None:
    contract = _minimal_contract()
    contract_path = _write_minimal_repo(tmp_path, contract)
    _write(
        tmp_path / "scripts/test_manifest.py",
        "SUITES = {'unit': ['tests/e2e/test_smoke.py']}\n"
        "SUITE_RUNTIME_MODE = {'unit': 'unit'}\n"
        "SUITE_ENV_PROFILE = {'unit': 'unit'}\n"
        "SUITE_PYTEST_ARGS = {'unit': ['-m', 'not integration_db']}\n",
    )

    findings = guard.evaluate_test_lane_governance(
        repo_root=tmp_path,
        contract_path=contract_path,
        write_report=False,
    )

    assert any(finding.rule == "unit-suite-contains-runtime-test-path" for finding in findings)
    assert any(finding.rule == "unit-suite-missing-runtime-exclusion" for finding in findings)


def test_test_lane_governance_guard_rejects_expired_quarantine(tmp_path: Path) -> None:
    contract = _minimal_contract()
    contract["quarantine_policy"]["quarantined_tests"] = [
        {
            "nodeid": "tests/e2e/test_flaky.py::test_flaky",
            "owner": "lotus-core/testing",
            "issue": "sgajbi/lotus-core#611",
            "reason": "demonstrate expiry enforcement",
            "quarantined_at": "2026-01-01",
            "expires_at": "2026-01-30",
        }
    ]
    contract_path = _write_minimal_repo(tmp_path, contract)

    findings = guard.evaluate_test_lane_governance(
        repo_root=tmp_path,
        contract_path=contract_path,
        write_report=False,
    )

    assert any(finding.rule == "quarantine-entry-expired" for finding in findings)
    assert any(finding.rule == "quarantine-entry-exceeds-maximum-days" for finding in findings)
