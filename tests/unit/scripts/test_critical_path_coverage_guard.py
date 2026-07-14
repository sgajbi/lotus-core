from __future__ import annotations

import copy
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.quality import critical_path_coverage_guard as guard
from scripts.quality.coverage_evidence.changed_source_evidence import (
    ChangedSourceFile,
    SourceChangeType,
)


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
            "minimum_measured_branch_coverage_percent": 85.0,
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


def _coverage_payload(
    *,
    covered_lines: int,
    statements: int,
    covered_branches: int = 4,
    branches: int = 4,
) -> dict[str, object]:
    return {
        "files": {
            "src/app/use_case.py": {
                "summary": {
                    "covered_lines": covered_lines,
                    "num_statements": statements,
                    "covered_branches": covered_branches,
                    "num_branches": branches,
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
    assert contract["aggregate_gate"]["coverage_json"].endswith("query-service-coverage.json")
    assert contract["changed_code_gate"]["coverage_json"].endswith("coverage.json")
    assert contract["changed_code_gate"]["unmeasured_critical_file_policy"] == "fail_closed"
    assert contract["changed_code_gate"]["minimum_measured_branch_coverage_percent"] == 85.0
    assert contract["changed_code_gate"]["deleted_paths_are_audit_only"] is True
    assert contract["changed_code_gate"]["rename_lineage_required"] is True


def test_guard_direct_script_entrypoint_resolves_coverage_evidence_package() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/quality/critical_path_coverage_guard.py", "--help"],
        cwd=guard.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--aggregate-coverage-json" in completed.stdout


def test_contract_validation_rejects_unknown_manifest_suite() -> None:
    contract = json.loads((guard.REPO_ROOT / guard.CONTRACT_PATH).read_text(encoding="utf-8"))
    mutated = copy.deepcopy(contract)
    mutated["critical_path_groups"][0]["required_manifest_suites"] = ["missing-suite"]

    findings = guard.validate_contract(contract=mutated)

    assert {
        "group_id": mutated["critical_path_groups"][0]["id"],
        "unknown_manifest_suites": ["missing-suite"],
    } in findings


def test_contract_validation_rejects_unknown_unmeasured_file_policy() -> None:
    contract = _minimal_contract()
    contract["changed_code_gate"]["unmeasured_critical_file_policy"] = "ignore"

    findings = guard.validate_contract(contract=contract)

    assert {
        "changed_code_gate": "invalid unmeasured_critical_file_policy",
        "value": "ignore",
    } in findings


def test_changed_code_report_classifies_measured_and_unmeasured_critical_files() -> None:
    report = guard.build_coverage_report(
        contract=_minimal_contract(),
        coverage_json=_coverage_payload(covered_lines=9, statements=10),
        changed_files=[
            ChangedSourceFile("M", SourceChangeType.MODIFIED, "src/app/use_case.py"),
            ChangedSourceFile("A", SourceChangeType.ADDED, "src/app/not_measured.py"),
            ChangedSourceFile("M", SourceChangeType.MODIFIED, "docs/readme.md"),
        ],
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


def test_coverage_report_keeps_aggregate_and_measured_source_totals_distinct() -> None:
    report = guard.build_coverage_report(
        contract=_minimal_contract(),
        coverage_json=_coverage_payload(covered_lines=9, statements=10),
        aggregate_coverage_json=_coverage_payload(covered_lines=99, statements=100),
        changed_files=[],
    )

    assert report["aggregate_coverage"]["percent_covered"] == 99.0
    assert report["measured_source_coverage"]["percent_covered"] == 90.0


def test_threshold_evaluation_rejects_low_measured_critical_group_coverage() -> None:
    report = guard.build_coverage_report(
        contract=_minimal_contract(),
        coverage_json=_coverage_payload(covered_lines=8, statements=10),
        changed_files=[ChangedSourceFile("M", SourceChangeType.MODIFIED, "src/app/use_case.py")],
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


def test_threshold_evaluation_rejects_low_changed_critical_branch_coverage() -> None:
    report = guard.build_coverage_report(
        contract=_minimal_contract(),
        coverage_json=_coverage_payload(
            covered_lines=10,
            statements=10,
            covered_branches=3,
            branches=4,
        ),
        changed_files=[ChangedSourceFile("M", SourceChangeType.MODIFIED, "src/app/use_case.py")],
    )

    findings = guard.evaluate_coverage_thresholds(report)

    assert {
        "changed_code": "measured critical changed-code branch coverage below minimum",
        "branch_coverage_percent": 75.0,
        "minimum": 85.0,
    } in findings


def test_changed_module_target_produces_real_line_and_branch_evidence(tmp_path: Path) -> None:
    module_path = tmp_path / "src" / "issue766_demo" / "replacement.py"
    _write(
        module_path,
        "def classify(value: int) -> str:\n"
        "    if value > 0:\n"
        "        return 'positive'\n"
        "    return 'non_positive'\n",
    )
    coverage_path = tmp_path / "coverage.json"
    script = textwrap.dedent(
        f"""
        import importlib
        from coverage import Coverage

        measured = Coverage(
            branch=True,
            config_file=False,
            source=["src.issue766_demo.replacement"],
        )
        measured.start()
        module = importlib.import_module("src.issue766_demo.replacement")
        assert module.classify(1) == "positive"
        assert module.classify(0) == "non_positive"
        measured.stop()
        measured.json_report(outfile={str(coverage_path)!r})
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    coverage_json = json.loads(coverage_path.read_text(encoding="utf-8"))
    contract = _minimal_contract()
    contract["critical_path_groups"][0]["source_globs"] = ["src/issue766_demo/**/*.py"]
    contract["changed_code_gate"]["minimum_measured_line_coverage_percent"] = 100.0
    contract["changed_code_gate"]["minimum_measured_branch_coverage_percent"] = 100.0
    report = guard.build_coverage_report(
        contract=contract,
        coverage_json=coverage_json,
        changed_files=[
            ChangedSourceFile(
                "R100",
                SourceChangeType.RENAMED,
                "src/issue766_demo/replacement.py",
                previous_path="src/issue766_demo/legacy.py",
                similarity_percent=100,
            )
        ],
    )

    changed = report["changed_code_coverage"]
    assert changed["measured_critical_changed_file_count"] == 1
    assert changed["measured_line_coverage_percent"] == 100.0
    assert changed["measured_branch_coverage_percent"] == 100.0
    assert guard.evaluate_coverage_thresholds(report) == []


def test_threshold_evaluation_fails_closed_for_unmeasured_changed_critical_source() -> None:
    contract = _minimal_contract()
    contract["changed_code_gate"]["unmeasured_critical_file_policy"] = "fail_closed"
    report = guard.build_coverage_report(
        contract=contract,
        coverage_json=_coverage_payload(covered_lines=10, statements=10),
        changed_files=[ChangedSourceFile("A", SourceChangeType.ADDED, "src/app/not_measured.py")],
    )

    findings = guard.evaluate_coverage_thresholds(report)

    assert {
        "code": guard.CHANGED_CRITICAL_SOURCE_UNMEASURED,
        "critical_path_groups": "demo_critical_path",
        "path": "src/app/not_measured.py",
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


def test_changed_code_report_retains_rename_and_delete_lineage() -> None:
    report = guard.build_coverage_report(
        contract=_minimal_contract(),
        coverage_json=_coverage_payload(covered_lines=9, statements=10),
        changed_files=[
            ChangedSourceFile(
                "R090",
                SourceChangeType.RENAMED,
                "src/app/use_case.py",
                previous_path="src/app/old_use_case.py",
                similarity_percent=90,
            ),
            ChangedSourceFile(
                "D",
                SourceChangeType.DELETED,
                None,
                previous_path="src/app/deleted.py",
            ),
        ],
    )

    changed = report["changed_code_coverage"]

    assert changed["changed_python_source_files"] == ["src/app/use_case.py"]
    assert changed["measured_critical_changed_file_count"] == 1
    assert changed["unmeasured_critical_changed_files"] == []
    assert changed["changed_file_lineage"] == [
        {
            "change_type": "renamed",
            "current_path": "src/app/use_case.py",
            "exists_at_head": True,
            "git_status": "R090",
            "previous_path": "src/app/old_use_case.py",
            "similarity_percent": 90,
        },
        {
            "change_type": "deleted",
            "current_path": None,
            "exists_at_head": False,
            "git_status": "D",
            "previous_path": "src/app/deleted.py",
            "similarity_percent": None,
        },
    ]


def test_changed_critical_source_paths_returns_only_current_governed_modules() -> None:
    paths = guard.changed_critical_source_paths(
        [
            ChangedSourceFile("M", SourceChangeType.MODIFIED, "src/app/use_case.py"),
            ChangedSourceFile("M", SourceChangeType.MODIFIED, "src/other/module.py"),
            ChangedSourceFile(
                "D",
                SourceChangeType.DELETED,
                None,
                previous_path="src/app/deleted.py",
            ),
            ChangedSourceFile("M", SourceChangeType.MODIFIED, "docs/example.py"),
        ],
        contract=_minimal_contract(),
    )

    assert paths == ["src/app/use_case.py"]
