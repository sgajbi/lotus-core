from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath

DEFAULT_BASELINE_PATH = Path("quality/module-size-baseline.v1.json")


@dataclass(frozen=True)
class SourceSizePolicy:
    threshold_lines: int
    scan_roots: tuple[str, ...]
    baseline_lines: dict[str, int]
    expires_on: dict[str, date]


def _normalized_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix().removeprefix("./")


def _required_text(entry: dict[str, object], field: str, *, path: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Module-size baseline entry {path} must define {field}.")
    return value


def load_policy(path: Path) -> SourceSizePolicy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "lotus.core.module-size-baseline.v1":
        raise ValueError("Module-size baseline has an unsupported schema_version.")
    threshold = payload.get("threshold_lines")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        raise ValueError("Module-size threshold_lines must be a positive integer.")
    roots = payload.get("scan_roots")
    if not isinstance(roots, list) or not roots:
        raise ValueError("Module-size scan_roots must be a non-empty list.")
    scan_roots = tuple(_normalized_path(str(root)) for root in roots)
    if len(set(scan_roots)) != len(scan_roots):
        raise ValueError("Module-size scan_roots must not contain duplicates.")
    if any(
        PurePosixPath(root).is_absolute() or ".." in PurePosixPath(root).parts
        for root in scan_roots
    ):
        raise ValueError("Module-size scan_roots must be repository-relative.")

    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Module-size baseline entries must be a list.")
    baseline_lines: dict[str, int] = {}
    expires_on: dict[str, date] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Module-size baseline entry {index} must be an object.")
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"Module-size baseline entry {index} must name a path.")
        normalized = _normalized_path(raw_path)
        if PurePosixPath(normalized).is_absolute() or ".." in PurePosixPath(normalized).parts:
            raise ValueError(f"Module-size baseline path must be repository-relative: {raw_path}")
        if normalized in baseline_lines:
            raise ValueError(f"Duplicate module-size baseline path: {normalized}")
        lines = entry.get("lines")
        if not isinstance(lines, int) or isinstance(lines, bool) or lines <= threshold:
            raise ValueError(
                f"Module-size baseline entry {normalized} must exceed threshold {threshold}."
            )
        for field in ("owner", "rationale", "issue"):
            _required_text(entry, field, path=normalized)
        expiry = _required_text(entry, "expires_on", path=normalized)
        try:
            expires_on[normalized] = date.fromisoformat(expiry)
        except ValueError as exc:
            raise ValueError(
                f"Module-size baseline entry {normalized} has invalid expires_on: {expiry}"
            ) from exc
        baseline_lines[normalized] = lines
    return SourceSizePolicy(
        threshold_lines=threshold,
        scan_roots=scan_roots,
        baseline_lines=baseline_lines,
        expires_on=expires_on,
    )


def tracked_python_line_counts(repo_root: Path, scan_roots: tuple[str, ...]) -> dict[str, int]:
    command = ["git", "-C", str(repo_root), "ls-files", "--", *scan_roots]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git ls-files failed")
    paths = sorted(
        {
            _normalized_path(path)
            for path in completed.stdout.splitlines()
            if path.strip().lower().endswith(".py")
        }
    )
    if not paths:
        raise ValueError("No tracked Python files matched the module-size scan roots.")
    line_counts: dict[str, int] = {}
    for path in paths:
        source_path = repo_root / Path(path)
        if not source_path.is_file():
            raise ValueError(f"Tracked Python source is missing from the checkout: {path}")
        line_counts[path] = len(source_path.read_text(encoding="utf-8").splitlines())
    return line_counts


def source_size_violations(
    line_counts: dict[str, int],
    *,
    policy: SourceSizePolicy,
    today: date | None = None,
) -> list[str]:
    if not line_counts:
        return ["no tracked Python modules were measured; refusing to pass an empty scan"]
    current_date = today or date.today()
    violations: list[str] = []
    observed_debt: set[str] = set()

    for path, lines in sorted(line_counts.items()):
        if lines <= policy.threshold_lines:
            if path in policy.baseline_lines:
                violations.append(
                    f"{path}: now has {lines} lines at or below {policy.threshold_lines}; "
                    "remove the resolved baseline"
                )
            continue
        observed_debt.add(path)
        baseline_lines = policy.baseline_lines.get(path)
        if baseline_lines is None:
            violations.append(
                f"{path}: {lines} lines exceeds {policy.threshold_lines} "
                "without a reviewed baseline"
            )
            continue
        if policy.expires_on[path] < current_date:
            violations.append(
                f"{path}: module-size baseline expired on {policy.expires_on[path].isoformat()}"
            )
        if lines > baseline_lines:
            violations.append(
                f"{path}: grew to {lines} lines from zero-headroom baseline {baseline_lines}"
            )
        elif lines < baseline_lines:
            violations.append(
                f"{path}: shrank to {lines} lines from baseline {baseline_lines}; "
                "ratchet the baseline"
            )

    for path in sorted(set(policy.baseline_lines) - observed_debt):
        if path not in line_counts:
            violations.append(f"{path}: baseline module was not observed; remove stale baseline")
    return violations


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when tracked Python modules exceed the zero-headroom size budget."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    repo_root = args.repo_root.resolve()
    baseline_path = args.baseline
    if not baseline_path.is_absolute():
        baseline_path = repo_root / baseline_path
    try:
        policy = load_policy(baseline_path)
        line_counts = tracked_python_line_counts(repo_root, policy.scan_roots)
        violations = source_size_violations(line_counts, policy=policy)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Module-size gate failed closed: {exc}", file=sys.stderr)
        return 1
    if violations:
        print("Module-size gate failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(
        "Module-size gate passed: "
        f"{len(line_counts)} tracked modules, threshold={policy.threshold_lines}, "
        f"baseline={len(policy.baseline_lines)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
