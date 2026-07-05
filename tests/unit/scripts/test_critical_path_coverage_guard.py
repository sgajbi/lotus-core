from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import critical_path_coverage_guard as guard


def _minimal_contract() -> dict[str, object]:
    return {
        "schema_version": "critical-path-coverage.v1",
        "owning_repository": "lotus-core",
        "aggregate_gate": {
            "command": "make coverage-gate",
            "minimum_line_coverage_percent": 98.0,
            "branch_coverage_required": True,
            "coverage_json": "output/coverage/coverage.json",
        },
        "changed_code_gate": {
            "base_ref_environment_variable": "LOTUS_COVERAGE_CHANGED_BASE",
            "default_base_ref": "origin/main",
            "minimum_measured_line_coverage_percent": 90.0,
            "unmeasured_critical_file_policy": "reported_requires_follow_up",
            "report_path": "output/coverage/critical-path-coverage-report.json",
        },
        "exception_policy": {
            "maximum_exception_days": 90,
            "required_fields": [
                "group_id",
                "path_glob",
                "reason",
                "owner",
                "follow_up_issue",
                "expires_on",
            ],
            "active_exceptions": [],
        },
        "critical_path_groups": [
            {
                "id": "demo_critical_path",
                "title": "Demo critical path",
                "risk": "Demonstrates threshold behavior.",
                "source_globs": ["src/app/**/*.py"],
                "minimum_measured_line_coverage_percent": 90.0,
                "minimum_measured_branch_coverage_percent": 80.0,
                "branch_coverage_required": True,
                "expected_test_families": ["unit"],
                "required_manifest_suites": ["unit"],
                "required_test_globs": ["tests/unit/**/*.py"],
            }
        ],
    }


def _coverage_payload(*, covered_lines: int, statements: int) -> dict[str, object]:
    return {
        "files": {
            "src/app/use_case.py": {
                "summary": {
                    "covered_lines": covered_lines,
                    "num_statements": statements,
                    "covered_branches": 4,
                    "num_branches": 4,
                }
            }
        },
        "totals": {
            "covered_lines": covered_lines,
            "num_statements": statements,
            "percent_covered": (covered_lines / statements) * 100,
        },
    }


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_current_critical_path_coverage_contract_is_valid() -> None:
    contract = json.loads((guard.REPO_ROOT / guard.CONTRACT_PATH).read_text(encoding="utf-8"))

    assert guard.validate_contract(contract=contract) == []


def test_contract_validation_rejects_unknown_manifest_suite() -> None:
    contract = json.loads((guard.REPO_ROOT / guard.CONTRACT_PATH).read_text(encoding="utf-8"))
    mutated = copy.deepcopy(contract)
    mutated["critical_path_groups"][0]["required_manifest_suites"] = ["missing-suite"]

    findings = guard.validate_contract(contract=mutated)

    assert {
        "group_id": mutated["critical_path_groups"][0]["id"],
        "unknown_manifest_suites": ["missing-suite"],
    } in findings


def test_changed_code_report_classifies_measured_and_unmeasured_critical_files() -> None:
    report = guard.build_coverage_report(
        contract=_minimal_contract(),
        coverage_json=_coverage_payload(covered_lines=9, statements=10),
        changed_files=["src/app/use_case.py", "src/app/not_measured.py", "docs/readme.md"],
    )

    changed = report["changed_code_coverage"]

    assert changed["measured_critical_changed_file_count"] == 1
    assert changed["measured_line_coverage_percent"] == 90.0
    assert changed["unmeasured_critical_changed_files"] == [
        {
            "path": "src/app/not_measured.py",
            "critical_path_groups": "demo_critical_path",
        }
    ]


def test_threshold_evaluation_rejects_low_measured_critical_group_coverage() -> None:
    report = guard.build_coverage_report(
        contract=_minimal_contract(),
        coverage_json=_coverage_payload(covered_lines=8, statements=10),
        changed_files=["src/app/use_case.py"],
    )

    findings = guard.evaluate_coverage_thresholds(report)

    assert {
        "group_id": "demo_critical_path",
        "line_coverage_percent": 80.0,
        "minimum": 90.0,
    } in findings
    assert {
        "changed_code": "measured critical changed-code coverage below minimum",
        "line_coverage_percent": 80.0,
        "minimum": 90.0,
    } in findings


def test_run_guard_writes_report_with_explicit_changed_files(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/standards/critical-path-coverage.v1.json", json.dumps(_minimal_contract())
    )
    _write(tmp_path / "src/app/use_case.py", "def demo():\n    return 1\n")
    _write(tmp_path / "tests/unit/test_use_case.py", "def test_demo():\n    assert True\n")
    _write(
        tmp_path / "coverage.json", json.dumps(_coverage_payload(covered_lines=10, statements=10))
    )

    findings, report = guard.run_guard(
        repo_root=tmp_path,
        contract_path=Path("docs/standards/critical-path-coverage.v1.json"),
        coverage_json_path=Path("coverage.json"),
        report_path=Path("output/coverage/report.json"),
        changed_base=None,
        changed_files=["src/app/use_case.py"],
        thresholds=True,
    )

    assert findings == []
    assert report["changed_code_coverage"]["measured_line_coverage_percent"] == 100.0
    assert (tmp_path / "output/coverage/report.json").exists()


def test_changed_files_from_git_uses_merge_base_diff_first(monkeypatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(args, **_kwargs):
        calls.append(list(args))
        return SimpleNamespace(returncode=0, stdout="src/app/use_case.py\n", stderr="")

    monkeypatch.setattr(guard.subprocess, "run", _fake_run)

    changed = guard._changed_files_from_git(repo_root=Path("."), base_ref="origin/main")

    assert changed == ["src/app/use_case.py"]
    assert calls[0] == ["git", "diff", "--name-only", "origin/main...HEAD"]
