from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _collect_python_files() -> list[Path]:
    src_root = ROOT / "src"
    return [p for p in src_root.rglob("*.py") if "__pycache__" not in p.parts]


def _scan_for_disallowed_patterns(files: list[Path], patterns: list[str]) -> list[str]:
    findings: list[str] = []
    for file_path in files:
        rel = file_path.relative_to(ROOT).as_posix()
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for idx, line in enumerate(content.splitlines(), start=1):
            for pattern in patterns:
                if pattern in line:
                    findings.append(f"{rel}:{idx}: disallowed pattern '{pattern}'")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check architecture boundary guardrails. "
            "Initial scope validates that removed ownership domains do not re-enter source imports."
        )
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with non-zero exit code on violations. Default mode prints findings only.",
    )
    args = parser.parse_args()

    disallowed_import_patterns = [
        "risk_analytics_engine",
        "performance_calculator_engine",
        "concentration_analytics_engine",
    ]

    files = _collect_python_files()
    findings = _scan_for_disallowed_patterns(files, disallowed_import_patterns)

    if findings:
        print("Architecture boundary guard findings:")
        for finding in findings:
            print(f" - {finding}")
        if args.strict:
            return 1
        return 0

    print("Architecture boundary guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
