"""Run governed suites and enforce aggregate plus changed-critical coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure repository root is importable when script runs directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Coverage.py enforces the displayed integer total for the combined
# branch-aware unit + integration-lite gate.
FAIL_UNDER = "98"
COVERAGE_OUTPUT_DIR = REPO_ROOT / "output" / "coverage"
COVERAGE_JSON = COVERAGE_OUTPUT_DIR / "coverage.json"
QUERY_SERVICE_COVERAGE_JSON = COVERAGE_OUTPUT_DIR / "query-service-coverage.json"
CRITICAL_PATH_REPORT = COVERAGE_OUTPUT_DIR / "critical-path-coverage-report.json"
UNIT_WARNING_BUDGET = 0
QUERY_SERVICE_INCLUDE = "src/services/query_service/app/*"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _changed_critical_paths() -> tuple[str, ...]:
    from scripts.quality.coverage_evidence.changed_source_evidence import (
        read_git_changed_sources,
    )
    from scripts.quality.critical_path_coverage_guard import (
        CONTRACT_PATH,
        changed_critical_source_paths,
    )

    contract = json.loads((REPO_ROOT / CONTRACT_PATH).read_text(encoding="utf-8"))
    changed_base = os.environ.get(
        "LOTUS_COVERAGE_CHANGED_BASE",
        str(contract["changed_code_gate"]["default_base_ref"]),
    )
    changes = read_git_changed_sources(repo_root=REPO_ROOT, base_ref=changed_base)
    return tuple(changed_critical_source_paths(changes, contract=contract))


def _coverage_sources(critical_paths: tuple[str, ...]) -> tuple[str, ...]:
    from scripts.quality.coverage_evidence.changed_source_evidence import coverage_source_target
    from scripts.quality.test_manifest import SOURCE

    changed_targets = (coverage_source_target(path) for path in critical_paths)
    return tuple(dict.fromkeys((SOURCE, *changed_targets)))


def _coverage_include(critical_paths: tuple[str, ...]) -> str:
    """Limit JSON evidence to aggregate scope plus exact changed critical files."""

    normalized_for_host = (str(Path(path)) for path in (QUERY_SERVICE_INCLUDE, *critical_paths))
    return ",".join(dict.fromkeys(normalized_for_host))


def main() -> int:
    from scripts.quality.test_manifest import run_suite
    from scripts.quality.warning_budget_gate import run_suite_with_warning_budget

    critical_paths = _changed_critical_paths()
    coverage_sources = _coverage_sources(critical_paths)

    for artifact in REPO_ROOT.glob(".coverage*"):
        if artifact.is_file():
            artifact.unlink()

    if (
        run_suite_with_warning_budget(
            suite="unit",
            max_warnings=UNIT_WARNING_BUDGET,
            with_coverage=True,
            coverage_sources=coverage_sources,
            coverage_file=".coverage.unit",
        )
        != 0
    ):
        return 1
    if (
        run_suite(
            "unit-db",
            with_coverage=True,
            coverage_sources=coverage_sources,
            coverage_file=".coverage.unit_db",
        )
        != 0
    ):
        return 1
    if (
        run_suite(
            "critical-db-coverage",
            with_coverage=True,
            coverage_sources=coverage_sources,
            coverage_file=".coverage.critical_db",
        )
        != 0
    ):
        return 1
    if (
        run_suite(
            "integration-lite",
            with_coverage=True,
            coverage_sources=coverage_sources,
            coverage_file=".coverage.integration_lite",
        )
        != 0
    ):
        return 1
    if (
        run_suite(
            "ops-contract",
            with_coverage=True,
            coverage_sources=coverage_sources,
            coverage_file=".coverage.ops_contract",
        )
        != 0
    ):
        return 1
    run(
        [
            sys.executable,
            "-m",
            "coverage",
            "combine",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            f"--include={QUERY_SERVICE_INCLUDE}",
            f"--fail-under={FAIL_UNDER}",
        ]
    )
    COVERAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-m",
            "coverage",
            "json",
            f"--include={QUERY_SERVICE_INCLUDE}",
            "-o",
            str(QUERY_SERVICE_COVERAGE_JSON),
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "coverage",
            "json",
            f"--include={_coverage_include(critical_paths)}",
            "-o",
            str(COVERAGE_JSON),
        ]
    )
    run(
        [
            sys.executable,
            "scripts/quality/critical_path_coverage_guard.py",
            "--coverage-json",
            str(COVERAGE_JSON.relative_to(REPO_ROOT)),
            "--aggregate-coverage-json",
            str(QUERY_SERVICE_COVERAGE_JSON.relative_to(REPO_ROOT)),
            "--output",
            str(CRITICAL_PATH_REPORT.relative_to(REPO_ROOT)),
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
