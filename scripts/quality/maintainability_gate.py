from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence

RANK_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
DEFAULT_ALLOWED_RANK = "C"


def maintainability_violations(
    report: Mapping[str, Mapping[str, object]],
    *,
    max_allowed_rank: str = DEFAULT_ALLOWED_RANK,
) -> list[str]:
    allowed_rank = max_allowed_rank.upper()
    allowed_score = RANK_ORDER[allowed_rank]
    violations: list[tuple[int, str, float]] = []

    for path, metrics in report.items():
        rank = str(metrics.get("rank", "")).upper()
        if rank not in RANK_ORDER:
            violations.append((len(RANK_ORDER), path, float(metrics.get("mi", 0.0))))
            continue
        if RANK_ORDER[rank] > allowed_score:
            violations.append((RANK_ORDER[rank], path, float(metrics.get("mi", 0.0))))

    return [
        f"{path}: maintainability rank {rank_from_score(score)} ({mi:.2f}) exceeds {allowed_rank}"
        for score, path, mi in sorted(violations)
    ]


def rank_from_score(score: int) -> str:
    for rank, rank_score in RANK_ORDER.items():
        if rank_score == score:
            return rank
    return "UNKNOWN"


def run_radon_maintainability(roots: Sequence[str]) -> dict[str, dict[str, object]]:
    command = [sys.executable, "-m", "radon", "mi", *roots, "-j"]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout, file=sys.stderr)
        raise SystemExit(completed.returncode)
    return json.loads(completed.stdout or "{}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when production source has D/E/F maintainability modules."
    )
    parser.add_argument("roots", nargs="*", default=["src"], help="Source roots to scan.")
    parser.add_argument(
        "--max-allowed-rank",
        default=DEFAULT_ALLOWED_RANK,
        choices=sorted(RANK_ORDER),
        help="Worst accepted Radon maintainability rank.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(tuple(argv or sys.argv[1:]))
    report = run_radon_maintainability(args.roots)
    violations = maintainability_violations(report, max_allowed_rank=args.max_allowed_rank)
    if violations:
        print("Maintainability gate failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print(
        "Maintainability gate passed: no source modules exceed "
        f"{args.max_allowed_rank.upper()} rank."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
