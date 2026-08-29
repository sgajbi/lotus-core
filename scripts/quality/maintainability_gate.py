from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

RANK_ORDER = {"A": 0, "B": 1, "C": 2}
DEFAULT_ALLOWED_RANK = "B"


def _normalized_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix().removeprefix("./")


def load_baseline(path: Path, *, max_allowed_rank: str) -> dict[str, tuple[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "lotus.core.maintainability-baseline.v1":
        raise ValueError("Maintainability baseline has an unsupported schema_version.")
    if payload.get("max_allowed_rank") != max_allowed_rank:
        raise ValueError(
            "Maintainability baseline max_allowed_rank does not match the active gate: "
            f"{payload.get('max_allowed_rank')!r} != {max_allowed_rank!r}."
        )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Maintainability baseline entries must be a list.")

    baseline: dict[str, tuple[str, float]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Maintainability baseline entry {index} must be an object.")
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"Maintainability baseline entry {index} must name a path.")
        normalized = _normalized_path(raw_path)
        if PurePosixPath(normalized).is_absolute() or ".." in PurePosixPath(normalized).parts:
            raise ValueError(
                f"Maintainability baseline path must be repository-relative: {raw_path}"
            )
        if normalized in baseline:
            raise ValueError(f"Duplicate maintainability baseline path: {normalized}")
        rank = str(entry.get("rank", "")).upper()
        if rank not in RANK_ORDER or RANK_ORDER[rank] <= RANK_ORDER[max_allowed_rank]:
            raise ValueError(
                f"Maintainability baseline entry {normalized} must exceed {max_allowed_rank}."
            )
        mi = entry.get("mi")
        if not isinstance(mi, int | float) or isinstance(mi, bool):
            raise ValueError(f"Maintainability baseline entry {normalized} must define numeric mi.")
        for field in ("owner", "rationale", "issue"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(
                    f"Maintainability baseline entry {normalized} must define {field}."
                )
        baseline[normalized] = (rank, float(mi))
    return baseline


def maintainability_violations(
    report: Mapping[str, Mapping[str, object]],
    *,
    max_allowed_rank: str = DEFAULT_ALLOWED_RANK,
    baseline: Mapping[str, tuple[str, float]] | None = None,
) -> list[str]:
    allowed_rank = max_allowed_rank.upper()
    allowed_score = RANK_ORDER[allowed_rank]
    normalized_report = {_normalized_path(path): metrics for path, metrics in report.items()}
    accepted_debt = dict(baseline or {})
    violations: list[str] = []

    if not normalized_report:
        return ["no tracked Python modules were analyzed; refusing to pass an empty scan"]

    observed_debt: set[str] = set()
    for path, metrics in sorted(normalized_report.items()):
        rank = str(metrics.get("rank", "")).upper()
        mi = float(metrics.get("mi", 0.0))
        if rank not in RANK_ORDER:
            violations.append(f"{path}: unknown maintainability rank {rank or 'EMPTY'} ({mi:.2f})")
            continue
        if RANK_ORDER[rank] <= allowed_score:
            if path in accepted_debt:
                baseline_rank, baseline_mi = accepted_debt[path]
                violations.append(
                    f"{path}: improved to rank {rank} ({mi:.2f}); remove stale baseline "
                    f"{baseline_rank} ({baseline_mi:.2f})"
                )
            continue

        observed_debt.add(path)
        accepted = accepted_debt.get(path)
        if accepted is None:
            violations.append(
                f"{path}: maintainability rank {rank} ({mi:.2f}) exceeds {allowed_rank} "
                "without a reviewed baseline"
            )
            continue
        baseline_rank, baseline_mi = accepted
        if rank != baseline_rank:
            violations.append(
                f"{path}: maintainability rank {rank} ({mi:.2f}) differs from baseline "
                f"{baseline_rank} ({baseline_mi:.2f})"
            )
        elif not math.isclose(mi, baseline_mi, abs_tol=1e-6):
            direction = "improved" if mi > baseline_mi else "worsened"
            violations.append(
                f"{path}: maintainability {direction} from baseline {baseline_rank} "
                f"({baseline_mi:.2f}) to {rank} ({mi:.2f}); ratchet the baseline"
            )

    for path in sorted(set(accepted_debt) - observed_debt):
        if path not in normalized_report:
            rank, mi = accepted_debt[path]
            violations.append(
                f"{path}: baseline {rank} ({mi:.2f}) was not observed; remove stale baseline"
            )
    return violations


def tracked_python_paths(roots: Sequence[str]) -> set[str]:
    command = ["git", "ls-files", "--", *roots]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git ls-files failed")
    paths = {
        _normalized_path(path)
        for path in completed.stdout.splitlines()
        if path.strip().lower().endswith(".py")
    }
    if not paths:
        raise ValueError("No tracked Python files matched the requested roots.")
    return paths


def run_radon_maintainability(roots: Sequence[str]) -> dict[str, dict[str, object]]:
    command = [sys.executable, "-m", "radon", "mi", *roots, "-j"]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    report = json.loads(completed.stdout or "{}")
    tracked = tracked_python_paths(roots)
    return {
        _normalized_path(path): metrics
        for path, metrics in report.items()
        if _normalized_path(path) in tracked
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when tracked Python source exceeds the maintainability ratchet."
    )
    parser.add_argument("roots", nargs="*", default=["src"], help="Source roots to scan.")
    parser.add_argument(
        "--max-allowed-rank",
        default=DEFAULT_ALLOWED_RANK,
        choices=sorted(RANK_ORDER),
        help="Worst accepted Radon maintainability rank.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Reviewed zero-headroom baseline for existing modules below the ceiling.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(tuple(argv or sys.argv[1:]))
    allowed_rank = args.max_allowed_rank.upper()
    try:
        baseline = (
            load_baseline(args.baseline, max_allowed_rank=allowed_rank) if args.baseline else {}
        )
        report = run_radon_maintainability(args.roots)
        violations = maintainability_violations(
            report,
            max_allowed_rank=allowed_rank,
            baseline=baseline,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Maintainability gate failed closed: {exc}", file=sys.stderr)
        return 1

    if violations:
        print("Maintainability gate failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print(
        "Maintainability gate passed: "
        f"{len(report)} tracked modules, ceiling={allowed_rank}, baseline={len(baseline)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
