"""Tests for governed warning-budget test execution."""

from __future__ import annotations

import subprocess
import sys

from scripts.quality import warning_budget_gate


def test_parse_warning_count_from_pytest_summary() -> None:
    output = "470 passed, 6 deselected, 8 warnings in 18.39s"
    assert warning_budget_gate.parse_warning_count(output) == 8


def test_parse_warning_count_when_no_summary_present() -> None:
    output = "12 passed in 0.20s"
    assert warning_budget_gate.parse_warning_count(output) == 0


def test_warning_budget_runner_preserves_manifest_coverage_options(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def completed_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "12 passed in 0.20s\n", "")

    monkeypatch.setattr(warning_budget_gate.subprocess, "run", completed_run)

    result = warning_budget_gate.run_suite_with_warning_budget(
        suite="unit",
        max_warnings=0,
        with_coverage=True,
        coverage_sources=("src.services.query_service.app", "src.services.core.domain.cost_basis"),
        coverage_file=".coverage.unit",
    )

    assert result == 0
    assert calls == [
        (
            [
                sys.executable,
                "scripts/quality/test_manifest.py",
                "--suite",
                "unit",
                "--with-coverage",
                "--coverage-source",
                "src.services.query_service.app",
                "--coverage-source",
                "src.services.core.domain.cost_basis",
                "--coverage-file",
                ".coverage.unit",
            ],
            {"capture_output": True, "text": True, "check": False},
        )
    ]


def test_warning_budget_runner_fails_closed_on_warning(monkeypatch, capsys) -> None:
    def completed_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, "12 passed, 1 warning in 0.20s\n", "")

    monkeypatch.setattr(warning_budget_gate.subprocess, "run", completed_run)

    result = warning_budget_gate.run_suite_with_warning_budget(suite="unit", max_warnings=0)

    assert result == 1
    assert "Warning budget exceeded" in capsys.readouterr().err
