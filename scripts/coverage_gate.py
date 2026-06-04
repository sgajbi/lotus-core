"""Run stable query-service suites with coverage and enforce a threshold."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure repository root is importable when script runs directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Coverage.py enforces the displayed integer total for the combined
# branch-aware unit + integration-lite gate.
FAIL_UNDER = "98"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    from scripts.test_manifest import run_suite

    for artifact in REPO_ROOT.glob(".coverage*"):
        if artifact.is_file():
            artifact.unlink()

    if run_suite("unit", with_coverage=True, coverage_file=".coverage.unit") != 0:
        return 1
    if (
        run_suite(
            "integration-lite",
            with_coverage=True,
            coverage_file=".coverage.integration_lite",
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
    run([sys.executable, "-m", "coverage", "report", f"--fail-under={FAIL_UNDER}"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
