"""Tests for combined coverage and warning evidence execution."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.quality import coverage_gate, test_manifest, warning_budget_gate
from scripts.quality import critical_path_coverage_guard as critical_guard
from scripts.quality.coverage_evidence import changed_source_evidence
from scripts.quality.coverage_evidence.changed_source_evidence import (
    ChangedSourceFile,
    SourceChangeType,
)


def _redirect_coverage_output(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "output" / "coverage"
    monkeypatch.setattr(coverage_gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(coverage_gate, "COVERAGE_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(coverage_gate, "COVERAGE_JSON", output_dir / "coverage.json")
    monkeypatch.setattr(
        coverage_gate,
        "QUERY_SERVICE_COVERAGE_JSON",
        output_dir / "query-service-coverage.json",
    )
    monkeypatch.setattr(
        coverage_gate,
        "CRITICAL_PATH_REPORT",
        output_dir / "critical-path-coverage-report.json",
    )


def test_coverage_gate_collects_unit_warnings_and_coverage_once(
    monkeypatch, tmp_path: Path
) -> None:
    _redirect_coverage_output(monkeypatch, tmp_path)
    warning_calls: list[dict[str, object]] = []
    suite_calls: list[tuple[str, dict[str, object]]] = []
    report_calls: list[list[str]] = []

    def run_warning_suite(**kwargs: object) -> int:
        warning_calls.append(kwargs)
        return 0

    def run_suite(name: str, **kwargs: object) -> int:
        suite_calls.append((name, kwargs))
        return 0

    monkeypatch.setattr(
        warning_budget_gate,
        "run_suite_with_warning_budget",
        run_warning_suite,
    )
    monkeypatch.setattr(test_manifest, "run_suite", run_suite)
    monkeypatch.setattr(coverage_gate, "run", report_calls.append)
    monkeypatch.setattr(
        coverage_gate,
        "_changed_critical_paths",
        lambda: ("src/services/core/domain/cost_basis.py",),
    )
    monkeypatch.setattr(
        coverage_gate,
        "_coverage_sources",
        lambda _critical_paths: (
            "src/services/query_service/app",
            "src.services.core.domain.cost_basis",
        ),
    )

    assert coverage_gate.main() == 0
    assert warning_calls == [
        {
            "suite": "unit",
            "max_warnings": 0,
            "with_coverage": True,
            "coverage_sources": (
                "src/services/query_service/app",
                "src.services.core.domain.cost_basis",
            ),
            "coverage_file": ".coverage.unit",
        }
    ]
    assert suite_calls == [
        (
            "integration-lite",
            {
                "with_coverage": True,
                "coverage_sources": (
                    "src/services/query_service/app",
                    "src.services.core.domain.cost_basis",
                ),
                "coverage_file": ".coverage.integration_lite",
            },
        ),
        (
            "ops-contract",
            {
                "with_coverage": True,
                "coverage_sources": (
                    "src/services/query_service/app",
                    "src.services.core.domain.cost_basis",
                ),
                "coverage_file": ".coverage.ops_contract",
            },
        ),
    ]
    assert len(report_calls) == 5
    assert f"--include={coverage_gate.QUERY_SERVICE_INCLUDE}" in report_calls[1]
    assert str(coverage_gate.QUERY_SERVICE_COVERAGE_JSON) in report_calls[2]
    expected_include = ",".join(
        (
            str(Path("src/services/query_service/app/*")),
            str(Path("src/services/core/domain/cost_basis.py")),
        )
    )
    assert f"--include={expected_include}" in report_calls[3]
    assert "--aggregate-coverage-json" in report_calls[4]


def test_coverage_gate_stops_when_unit_warning_evidence_fails(monkeypatch, tmp_path: Path) -> None:
    _redirect_coverage_output(monkeypatch, tmp_path)
    monkeypatch.setattr(
        warning_budget_gate,
        "run_suite_with_warning_budget",
        lambda **kwargs: 1,
    )
    monkeypatch.setattr(coverage_gate, "_changed_critical_paths", lambda: ())
    monkeypatch.setattr(coverage_gate, "_coverage_sources", lambda _critical_paths: ())

    assert coverage_gate.main() == 1


def test_coverage_gate_stops_when_operations_contract_coverage_fails(
    monkeypatch, tmp_path: Path
) -> None:
    _redirect_coverage_output(monkeypatch, tmp_path)
    suite_calls: list[str] = []

    monkeypatch.setattr(
        warning_budget_gate,
        "run_suite_with_warning_budget",
        lambda **_kwargs: 0,
    )

    def run_suite(name: str, **_kwargs: object) -> int:
        suite_calls.append(name)
        return 1 if name == "ops-contract" else 0

    monkeypatch.setattr(test_manifest, "run_suite", run_suite)
    monkeypatch.setattr(coverage_gate, "run", lambda _command: None)
    monkeypatch.setattr(coverage_gate, "_changed_critical_paths", lambda: ())
    monkeypatch.setattr(coverage_gate, "_coverage_sources", lambda _critical_paths: ())

    assert coverage_gate.main() == 1
    assert suite_calls == ["integration-lite", "ops-contract"]


def test_operations_contract_suite_includes_control_plane_router_contracts() -> None:
    assert (
        "tests/integration/services/query_control_plane_service/"
        "test_operations_router_dependency.py" in test_manifest.get_suite("ops-contract")
    )


def test_coverage_scope_adds_current_changed_critical_sources(monkeypatch, tmp_path: Path) -> None:
    _redirect_coverage_output(monkeypatch, tmp_path)
    contract_path = tmp_path / critical_guard.CONTRACT_PATH
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        json.dumps(
            {
                "changed_code_gate": {"default_base_ref": "origin/main"},
                "critical_path_groups": [
                    {
                        "id": "cost_basis",
                        "source_globs": ["src/services/core/app/**/*.py", "alembic/**/*.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        changed_source_evidence,
        "read_git_changed_sources",
        lambda **_kwargs: [
            ChangedSourceFile(
                "A",
                SourceChangeType.ADDED,
                "src/services/core/app/use_case.py",
            ),
            ChangedSourceFile(
                "A",
                SourceChangeType.ADDED,
                "alembic/versions/abc123_add_table.py",
            ),
        ],
    )

    critical_paths = coverage_gate._changed_critical_paths()
    sources = coverage_gate._coverage_sources(critical_paths)

    assert critical_paths == (
        "alembic/versions/abc123_add_table.py",
        "src/services/core/app/use_case.py",
    )
    assert sources == (
        test_manifest.SOURCE,
        "./alembic",
        "src/services/core/app",
    )
    assert coverage_gate._coverage_include(critical_paths) == ",".join(
        (
            str(Path("src/services/query_service/app/*")),
            str(Path("alembic/versions/abc123_add_table.py")),
            str(Path("src/services/core/app/use_case.py")),
        )
    )


def test_coverage_scope_deduplicates_changed_files_in_one_source_directory() -> None:
    sources = coverage_gate._coverage_sources(
        (
            "src/services/core/app/first.py",
            "src/services/core/app/second.py",
        )
    )

    assert sources == (test_manifest.SOURCE, "src/services/core/app")
