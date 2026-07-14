"""Run a test suite and enforce a warning budget."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

WARNING_SUMMARY_RE = re.compile(r"(?P<count>\d+)\s+warnings?\s+in\s+", re.IGNORECASE)


def parse_warning_count(output: str) -> int:
    matches = list(WARNING_SUMMARY_RE.finditer(output))
    if not matches:
        return 0
    return int(matches[-1].group("count"))


def run_suite_with_warning_budget(
    *,
    suite: str,
    max_warnings: int,
    quiet: bool = False,
    with_coverage: bool = False,
    coverage_file: str | None = None,
) -> int:
    """Run one manifest suite and fail when its warning budget is exceeded."""
    cmd = [sys.executable, "scripts/quality/test_manifest.py", "--suite", suite]
    if quiet:
        cmd.append("--quiet")
    if with_coverage:
        cmd.append("--with-coverage")
    if coverage_file is not None:
        cmd.extend(["--coverage-file", coverage_file])

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    warning_count = parse_warning_count((proc.stdout or "") + "\n" + (proc.stderr or ""))
    print(f"Warning budget: suite={suite}, warnings={warning_count}, max={max_warnings}")

    if proc.returncode != 0:
        return proc.returncode

    if warning_count > max_warnings:
        print(
            f"Warning budget exceeded for suite '{suite}': {warning_count} > {max_warnings}",
            file=sys.stderr,
        )
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce warning budget for a pytest suite.")
    parser.add_argument(
        "--suite", default="unit", help="Suite name from scripts/quality/test_manifest.py."
    )
    parser.add_argument("--max-warnings", type=int, default=0, help="Max warnings allowed.")
    parser.add_argument("--quiet", action="store_true", help="Pass -q to pytest.")
    parser.add_argument(
        "--with-coverage",
        action="store_true",
        help="Collect coverage during this warning-budget execution.",
    )
    parser.add_argument(
        "--coverage-file",
        default=None,
        help="Set COVERAGE_FILE through the governed test manifest.",
    )
    args = parser.parse_args()

    return run_suite_with_warning_budget(
        suite=args.suite,
        max_warnings=args.max_warnings,
        quiet=args.quiet,
        with_coverage=args.with_coverage,
        coverage_file=args.coverage_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
