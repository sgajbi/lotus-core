"""Tests for combined coverage and warning evidence execution."""

from __future__ import annotations

from pathlib import Path

from scripts.quality import coverage_gate, test_manifest, warning_budget_gate


def _redirect_coverage_output(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "output" / "coverage"
    monkeypatch.setattr(coverage_gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(coverage_gate, "COVERAGE_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(coverage_gate, "COVERAGE_JSON", output_dir / "coverage.json")
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

    assert coverage_gate.main() == 0
    assert warning_calls == [
        {
            "suite": "unit",
            "max_warnings": 0,
            "with_coverage": True,
            "coverage_file": ".coverage.unit",
        }
    ]
    assert suite_calls == [
        (
            "integration-lite",
            {
                "with_coverage": True,
                "coverage_file": ".coverage.integration_lite",
            },
        )
    ]
    assert len(report_calls) == 4


def test_coverage_gate_stops_when_unit_warning_evidence_fails(monkeypatch, tmp_path: Path) -> None:
    _redirect_coverage_output(monkeypatch, tmp_path)
    monkeypatch.setattr(
        warning_budget_gate,
        "run_suite_with_warning_budget",
        lambda **kwargs: 1,
    )

    assert coverage_gate.main() == 1
