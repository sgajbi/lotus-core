from __future__ import annotations

import argparse
import json
import math

# Fixed Git/Radon executables use argument vectors and never invoke a shell.
import subprocess  # nosec B404
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path, PurePosixPath

from radon.metrics import mi_parameters

RANK_ORDER = {"A": 0, "B": 1, "C": 2}
DEFAULT_ALLOWED_RANK = "B"


def _normalized_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix().removeprefix("./")


def _validated_roots(roots: Sequence[str]) -> tuple[str, ...]:
    validated: list[str] = []
    for root in roots:
        normalized = _normalized_path(root)
        if (
            not root.strip()
            or root.startswith("-")
            or Path(root).is_absolute()
            or PurePosixPath(normalized).is_absolute()
            or ".." in PurePosixPath(normalized).parts
        ):
            raise ValueError(f"Maintainability scan root must be repository-relative: {root}")
        validated.append(normalized)
    if not validated:
        raise ValueError("Maintainability scan roots must not be empty.")
    return tuple(validated)


def load_baseline(
    path: Path, *, max_allowed_rank: str
) -> dict[str, tuple[str, float, float | None]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "lotus.core.maintainability-baseline.v1":
        raise ValueError("Maintainability baseline has an unsupported schema_version.")
    if payload.get("max_allowed_rank") != max_allowed_rank:
        raise ValueError(
            "Maintainability baseline max_allowed_rank does not match the active gate: "
            f"{payload.get('max_allowed_rank')!r} != {max_allowed_rank!r}."
        )
    if payload.get("tracked_files_only") is not True:
        raise ValueError("Maintainability baseline must set tracked_files_only to true.")
    try:
        date.fromisoformat(str(payload.get("recorded_on", "")))
    except ValueError as exc:
        raise ValueError("Maintainability baseline recorded_on must be an ISO date.") from exc
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Maintainability baseline entries must be a list.")

    baseline: dict[str, tuple[str, float, float | None]] = {}
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
        raw_mi = entry.get("raw_mi")
        if float(mi) == 0.0 and (not isinstance(raw_mi, int | float) or isinstance(raw_mi, bool)):
            raise ValueError(
                f"Maintainability baseline entry {normalized} at the MI floor must define "
                "numeric raw_mi."
            )
        if raw_mi is not None and (not isinstance(raw_mi, int | float) or isinstance(raw_mi, bool)):
            raise ValueError(f"Maintainability baseline entry {normalized} raw_mi must be numeric.")
        for field in ("owner", "rationale", "issue"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(
                    f"Maintainability baseline entry {normalized} must define {field}."
                )
        baseline[normalized] = (
            rank,
            float(mi),
            float(raw_mi) if raw_mi is not None else None,
        )
    return baseline


def maintainability_violations(
    report: Mapping[str, Mapping[str, object]],
    *,
    max_allowed_rank: str = DEFAULT_ALLOWED_RANK,
    baseline: Mapping[str, tuple[str, float, float | None]] | None = None,
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
        raw_mi = metrics.get("mi")
        if not isinstance(raw_mi, int | float) or isinstance(raw_mi, bool):
            violations.append(f"{path}: maintainability index is missing or non-numeric")
            continue
        mi = float(raw_mi)
        if rank not in RANK_ORDER:
            violations.append(f"{path}: unknown maintainability rank {rank or 'EMPTY'} ({mi:.2f})")
            continue
        if RANK_ORDER[rank] <= allowed_score:
            if path in accepted_debt:
                baseline_rank, baseline_mi, _ = accepted_debt[path]
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
        baseline_rank, baseline_mi, baseline_raw_mi = accepted
        if not math.isclose(mi, baseline_mi, abs_tol=1e-6):
            direction = "improved" if mi > baseline_mi else "worsened"
            violations.append(
                f"{path}: maintainability {direction} from baseline {baseline_rank} "
                f"({baseline_mi:.2f}) to {rank} ({mi:.2f}); ratchet the baseline"
            )
        elif baseline_mi == 0.0:
            raw_mi = metrics.get("raw_mi")
            if (
                baseline_raw_mi is None
                or not isinstance(raw_mi, int | float)
                or isinstance(raw_mi, bool)
            ):
                violations.append(
                    f"{path}: clamped maintainability requires numeric raw_mi evidence"
                )
            elif not math.isclose(float(raw_mi), baseline_raw_mi, abs_tol=1e-6):
                direction = "improved" if float(raw_mi) > baseline_raw_mi else "worsened"
                violations.append(
                    f"{path}: unclamped maintainability {direction} from baseline "
                    f"{baseline_raw_mi:.2f} to {float(raw_mi):.2f}; ratchet the baseline"
                )

    for path in sorted(set(accepted_debt) - observed_debt):
        if path not in normalized_report:
            rank, mi, _ = accepted_debt[path]
            violations.append(
                f"{path}: baseline {rank} ({mi:.2f}) was not observed; remove stale baseline"
            )
    return violations


def unclamped_maintainability_index(source: str) -> float:
    raw_volume, raw_complexity, raw_logical_lines, raw_comments = mi_parameters(source)
    volume = float(raw_volume)
    complexity = float(raw_complexity)
    logical_lines = float(raw_logical_lines)
    comments = float(raw_comments)
    if volume <= 0 or logical_lines <= 0:
        return 100.0
    non_normalized = (
        171
        - 5.2 * math.log(volume)
        - 0.23 * complexity
        - 16.2 * math.log(logical_lines)
        + 50 * math.sin(math.sqrt(2.46 * math.radians(comments)))
    )
    return float(non_normalized * 100 / 171.0)


def tracked_python_paths(roots: Sequence[str]) -> set[str]:
    validated_roots = _validated_roots(roots)
    command = ["git", "ls-files", "--", *validated_roots]
    # The executable is fixed; roots are validated and follow Git's option terminator.
    completed = subprocess.run(  # nosec B603
        command, check=False, capture_output=True, text=True
    )
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
    validated_roots = _validated_roots(roots)
    command = [sys.executable, "-m", "radon", "mi", *validated_roots, "-j"]
    # The interpreter/module are fixed, roots are validated, and no shell is used.
    completed = subprocess.run(  # nosec B603
        command, check=False, capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    report = json.loads(completed.stdout or "{}")
    tracked = tracked_python_paths(validated_roots)
    tracked_report: dict[str, dict[str, object]] = {}
    for path, metrics in report.items():
        normalized = _normalized_path(path)
        if normalized not in tracked:
            continue
        tracked_metrics = dict(metrics)
        if tracked_metrics.get("mi") == 0.0:
            source = Path(normalized).read_text(encoding="utf-8")
            tracked_metrics["raw_mi"] = unclamped_maintainability_index(source)
        tracked_report[normalized] = tracked_metrics
    return tracked_report


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
