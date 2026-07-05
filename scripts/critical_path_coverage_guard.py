"""Validate and report critical-path and changed-code coverage posture."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTRACT_PATH = Path("docs/standards/critical-path-coverage.v1.json")
DEFAULT_REPORT_PATH = Path("output/coverage/critical-path-coverage-report.json")
SCHEMA_VERSION = "critical-path-coverage.v1"


@dataclass(frozen=True)
class CoverageSummary:
    covered_lines: int = 0
    statements: int = 0
    covered_branches: int = 0
    branches: int = 0

    @property
    def line_percent(self) -> float | None:
        if self.statements == 0:
            return None
        return round((self.covered_lines / self.statements) * 100, 2)

    @property
    def branch_percent(self) -> float | None:
        if self.branches == 0:
            return None
        return round((self.covered_branches / self.branches) * 100, 2)


def _relative(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_files(*, repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode == 0:
        return [_normalize_path(line) for line in completed.stdout.splitlines() if line.strip()]
    return [
        _relative(path, repo_root=repo_root)
        for path in repo_root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = _normalize_path(path)
    return any(_glob_matches(normalized, _normalize_path(pattern)) for pattern in patterns)


def _glob_matches(path: str, pattern: str) -> bool:
    regex_parts = ["^"]
    index = 0
    while index < len(pattern):
        if pattern[index : index + 3] == "**/":
            regex_parts.append("(?:.*/)?")
            index += 3
        elif pattern[index : index + 2] == "**":
            regex_parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            regex_parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            regex_parts.append("[^/]")
            index += 1
        else:
            regex_parts.append(re.escape(pattern[index]))
            index += 1
    regex_parts.append("$")
    return re.match("".join(regex_parts), path) is not None


def _matching_files(patterns: list[str], *, repo_root: Path) -> list[str]:
    files = _repo_files(repo_root=repo_root)
    return sorted(path for path in files if _matches_any(path, patterns))


def _validate_group_contract(
    group: dict[str, Any],
    *,
    repo_root: Path,
    known_suites: set[str],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    group_id = str(group.get("id", ""))
    if not group_id:
        findings.append({"group": group, "missing": "id"})
        return findings

    source_globs = group.get("source_globs")
    if not isinstance(source_globs, list) or not source_globs:
        findings.append({"group_id": group_id, "missing": "source_globs"})
    else:
        missing_globs = [
            pattern
            for pattern in source_globs
            if not _matching_files([str(pattern)], repo_root=repo_root)
        ]
        if missing_globs:
            findings.append({"group_id": group_id, "source_globs_without_matches": missing_globs})

    test_globs = group.get("required_test_globs")
    if not isinstance(test_globs, list) or not test_globs:
        findings.append({"group_id": group_id, "missing": "required_test_globs"})
    else:
        missing_test_globs = [
            pattern
            for pattern in test_globs
            if not _matching_files([str(pattern)], repo_root=repo_root)
        ]
        if missing_test_globs:
            findings.append(
                {"group_id": group_id, "test_globs_without_matches": missing_test_globs}
            )

    suites = group.get("required_manifest_suites")
    if not isinstance(suites, list) or not suites:
        findings.append({"group_id": group_id, "missing": "required_manifest_suites"})
    else:
        unknown = sorted(str(suite) for suite in suites if str(suite) not in known_suites)
        if unknown:
            findings.append({"group_id": group_id, "unknown_manifest_suites": unknown})

    for field in (
        "minimum_measured_line_coverage_percent",
        "minimum_measured_branch_coverage_percent",
    ):
        value = group.get(field)
        if not isinstance(value, int | float) or not (0 <= float(value) <= 100):
            findings.append({"group_id": group_id, "invalid_percent_field": field, "value": value})

    if group.get("branch_coverage_required") is not True:
        findings.append(
            {
                "group_id": group_id,
                "branch_coverage_required": group.get("branch_coverage_required"),
            }
        )

    return findings


def _validate_exception_contract(
    contract: dict[str, Any],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    policy = contract.get("exception_policy", {})
    required = set(policy.get("required_fields", []))
    maximum_days = int(policy.get("maximum_exception_days", 0))
    group_ids = {str(group.get("id")) for group in contract.get("critical_path_groups", [])}
    today = date.today()

    for exception in policy.get("active_exceptions", []):
        if not isinstance(exception, dict):
            findings.append({"invalid_exception": exception})
            continue
        missing = sorted(required - set(exception.keys()))
        if missing:
            findings.append({"exception": exception, "missing_fields": missing})
        if exception.get("group_id") not in group_ids:
            findings.append({"exception": exception, "unknown_group_id": exception.get("group_id")})
        try:
            expires_on = date.fromisoformat(str(exception.get("expires_on")))
        except ValueError:
            findings.append(
                {"exception": exception, "invalid_expires_on": exception.get("expires_on")}
            )
            continue
        if expires_on < today:
            findings.append({"exception": exception, "expired": True})
        if maximum_days and (expires_on - today).days > maximum_days:
            findings.append({"exception": exception, "expiry_exceeds_maximum_days": maximum_days})
    return findings


def validate_contract(
    *,
    contract: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, object]]:
    from scripts.test_manifest import SUITES

    findings: list[dict[str, object]] = []
    if contract.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            {
                "contract": CONTRACT_PATH.as_posix(),
                "invalid_schema_version": contract.get("schema_version"),
            }
        )

    aggregate = contract.get("aggregate_gate", {})
    if aggregate.get("branch_coverage_required") is not True:
        findings.append({"aggregate_gate": "branch_coverage_required must be true"})
    if float(aggregate.get("minimum_line_coverage_percent", -1)) < 0:
        findings.append({"aggregate_gate": "minimum_line_coverage_percent must be non-negative"})

    changed = contract.get("changed_code_gate", {})
    if not changed.get("report_path"):
        findings.append({"changed_code_gate": "missing report_path"})
    if float(changed.get("minimum_measured_line_coverage_percent", -1)) < 0:
        findings.append(
            {"changed_code_gate": "minimum_measured_line_coverage_percent must be non-negative"}
        )

    groups = contract.get("critical_path_groups")
    if not isinstance(groups, list) or not groups:
        findings.append({"contract": CONTRACT_PATH.as_posix(), "missing": "critical_path_groups"})
        return findings

    seen: set[str] = set()
    known_suites = set(SUITES)
    for group in groups:
        if not isinstance(group, dict):
            findings.append({"invalid_group": group})
            continue
        group_id = str(group.get("id", ""))
        if group_id in seen:
            findings.append({"duplicate_group_id": group_id})
        seen.add(group_id)
        findings.extend(
            _validate_group_contract(group, repo_root=repo_root, known_suites=known_suites)
        )

    findings.extend(_validate_exception_contract(contract))
    return findings


def _coverage_summary_for_file(file_payload: dict[str, Any]) -> CoverageSummary:
    summary = file_payload.get("summary", {})
    return CoverageSummary(
        covered_lines=int(summary.get("covered_lines", 0)),
        statements=int(summary.get("num_statements", 0)),
        covered_branches=int(summary.get("covered_branches", 0)),
        branches=int(summary.get("num_branches", 0)),
    )


def _combine_summaries(summaries: list[CoverageSummary]) -> CoverageSummary:
    return CoverageSummary(
        covered_lines=sum(summary.covered_lines for summary in summaries),
        statements=sum(summary.statements for summary in summaries),
        covered_branches=sum(summary.covered_branches for summary in summaries),
        branches=sum(summary.branches for summary in summaries),
    )


def _coverage_files(coverage_json: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not coverage_json:
        return {}
    return {
        _normalize_path(path): payload
        for path, payload in coverage_json.get("files", {}).items()
        if isinstance(payload, dict)
    }


def _changed_files_from_git(*, repo_root: Path, base_ref: str | None) -> list[str]:
    if not base_ref:
        return []
    candidates = ([base_ref, "HEAD"], [f"{base_ref}...HEAD"])
    for args in candidates:
        completed = subprocess.run(
            ["git", "diff", "--name-only", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode == 0:
            return [_normalize_path(line) for line in completed.stdout.splitlines() if line.strip()]
    return []


def _group_report(
    group: dict[str, Any],
    *,
    coverage_files: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_globs = [str(pattern) for pattern in group["source_globs"]]
    measured_files = sorted(path for path in coverage_files if _matches_any(path, source_globs))
    summary = _combine_summaries(
        [_coverage_summary_for_file(coverage_files[path]) for path in measured_files]
    )
    return {
        "id": group["id"],
        "title": group["title"],
        "measured_files": measured_files,
        "measured_file_count": len(measured_files),
        "line_coverage_percent": summary.line_percent,
        "branch_coverage_percent": summary.branch_percent,
        "minimum_measured_line_coverage_percent": group["minimum_measured_line_coverage_percent"],
        "minimum_measured_branch_coverage_percent": group[
            "minimum_measured_branch_coverage_percent"
        ],
        "expected_test_families": group["expected_test_families"],
        "required_manifest_suites": group["required_manifest_suites"],
    }


def _changed_report(
    *,
    changed_files: list[str],
    contract: dict[str, Any],
    coverage_files: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    critical_changed: list[dict[str, Any]] = []
    unmeasured: list[dict[str, str]] = []
    measured_summaries: list[CoverageSummary] = []
    changed_python_source = [
        path for path in changed_files if path.endswith(".py") and path.startswith("src/")
    ]

    for path in changed_python_source:
        matched_groups = [
            str(group["id"])
            for group in contract["critical_path_groups"]
            if _matches_any(path, [str(pattern) for pattern in group["source_globs"]])
        ]
        if not matched_groups:
            continue
        record: dict[str, Any] = {"path": path, "critical_path_groups": matched_groups}
        if path in coverage_files:
            summary = _coverage_summary_for_file(coverage_files[path])
            measured_summaries.append(summary)
            record["line_coverage_percent"] = summary.line_percent
            record["branch_coverage_percent"] = summary.branch_percent
        else:
            unmeasured.append({"path": path, "critical_path_groups": ",".join(matched_groups)})
            record["coverage_status"] = "not_measured_by_current_coverage_json"
        critical_changed.append(record)

    combined = _combine_summaries(measured_summaries)
    return {
        "changed_python_source_files": changed_python_source,
        "critical_changed_files": critical_changed,
        "measured_critical_changed_file_count": len(measured_summaries),
        "unmeasured_critical_changed_files": unmeasured,
        "measured_line_coverage_percent": combined.line_percent,
        "measured_branch_coverage_percent": combined.branch_percent,
        "minimum_measured_line_coverage_percent": contract["changed_code_gate"][
            "minimum_measured_line_coverage_percent"
        ],
        "unmeasured_critical_file_policy": contract["changed_code_gate"][
            "unmeasured_critical_file_policy"
        ],
    }


def build_coverage_report(
    *,
    contract: dict[str, Any],
    coverage_json: dict[str, Any] | None,
    changed_files: list[str],
) -> dict[str, Any]:
    coverage_files = _coverage_files(coverage_json)
    group_reports = [
        _group_report(group, coverage_files=coverage_files)
        for group in contract["critical_path_groups"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "owning_repository": contract["owning_repository"],
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "aggregate_coverage": (coverage_json or {}).get("totals", {}),
        "changed_code_coverage": _changed_report(
            changed_files=changed_files,
            contract=contract,
            coverage_files=coverage_files,
        ),
        "critical_path_coverage": group_reports,
    }


def evaluate_coverage_thresholds(report: dict[str, Any]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for group in report["critical_path_coverage"]:
        if group["line_coverage_percent"] is not None and (
            group["line_coverage_percent"] < group["minimum_measured_line_coverage_percent"]
        ):
            findings.append(
                {
                    "group_id": group["id"],
                    "line_coverage_percent": group["line_coverage_percent"],
                    "minimum": group["minimum_measured_line_coverage_percent"],
                }
            )
        if group["branch_coverage_percent"] is not None and (
            group["branch_coverage_percent"] < group["minimum_measured_branch_coverage_percent"]
        ):
            findings.append(
                {
                    "group_id": group["id"],
                    "branch_coverage_percent": group["branch_coverage_percent"],
                    "minimum": group["minimum_measured_branch_coverage_percent"],
                }
            )

    changed = report["changed_code_coverage"]
    if changed["measured_line_coverage_percent"] is not None and (
        changed["measured_line_coverage_percent"]
        < changed["minimum_measured_line_coverage_percent"]
    ):
        findings.append(
            {
                "changed_code": "measured critical changed-code coverage below minimum",
                "line_coverage_percent": changed["measured_line_coverage_percent"],
                "minimum": changed["minimum_measured_line_coverage_percent"],
            }
        )
    return findings


def run_guard(
    *,
    repo_root: Path,
    contract_path: Path,
    coverage_json_path: Path | None,
    report_path: Path,
    changed_base: str | None,
    changed_files: list[str] | None,
    thresholds: bool,
) -> tuple[list[dict[str, object]], dict[str, Any]]:
    contract = _load_json(repo_root / contract_path)
    findings = validate_contract(contract=contract, repo_root=repo_root)

    coverage_json = None
    if coverage_json_path is not None and (repo_root / coverage_json_path).exists():
        coverage_json = _load_json(repo_root / coverage_json_path)

    resolved_changed_files = changed_files
    if resolved_changed_files is None:
        resolved_changed_files = _changed_files_from_git(repo_root=repo_root, base_ref=changed_base)

    report = build_coverage_report(
        contract=contract,
        coverage_json=coverage_json,
        changed_files=resolved_changed_files,
    )
    if thresholds:
        findings.extend(evaluate_coverage_thresholds(report))

    output = repo_root / report_path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return findings, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate critical-path coverage contract and write changed-code coverage report."
        )
    )
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--coverage-json", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--changed-base",
        default=os.environ.get("LOTUS_COVERAGE_CHANGED_BASE", "origin/main"),
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=None,
        help="Supply changed files explicitly; repeat for multiple files. Skips git diff.",
    )
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help=(
            "Validate the contract and write a report without enforcing measured "
            "coverage thresholds."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings, report = run_guard(
        repo_root=REPO_ROOT,
        contract_path=args.contract,
        coverage_json_path=args.coverage_json,
        report_path=args.output,
        changed_base=args.changed_base,
        changed_files=args.changed_file,
        thresholds=not args.contract_only,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if findings:
        print("Critical-path coverage guard failed:")
        print(json.dumps(findings, indent=2, sort_keys=True))
        return 1
    print(f"Critical-path coverage guard passed. Report: {args.output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
