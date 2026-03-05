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


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce warning budget for a pytest suite.")
    parser.add_argument("--suite", default="unit", help="Suite name from scripts/test_manifest.py.")
    parser.add_argument("--max-warnings", type=int, default=0, help="Max warnings allowed.")
    parser.add_argument("--quiet", action="store_true", help="Pass -q to pytest.")
    args = parser.parse_args()

    cmd = [sys.executable, "scripts/test_manifest.py", "--suite", args.suite]
    if args.quiet:
        cmd.append("--quiet")

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    warning_count = parse_warning_count((proc.stdout or "") + "\n" + (proc.stderr or ""))
    print(f"Warning budget: suite={args.suite}, warnings={warning_count}, max={args.max_warnings}")

    if proc.returncode != 0:
        return proc.returncode

    if warning_count > args.max_warnings:
        print(
            f"Warning budget exceeded for suite '{args.suite}': "
            f"{warning_count} > {args.max_warnings}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
