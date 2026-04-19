"""Generate institutional sign-off evidence pack from latest gate artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from numbers import Real
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ArtifactStatus:
    name: str
    path: str | None
    passed: bool
    summary: str


def _latest_artifact(output_dir: Path, pattern: str) -> Path | None:
    # CI artifact downloads can include nested paths.
    # Use recursive discovery so sign-off generation remains robust
    # regardless of upload path prefixes.
    matches = sorted(output_dir.rglob(pattern), key=lambda p: p.stat().st_mtime)
    if not matches:
        return None
    return matches[-1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _docker_smoke_status(path: Path | None) -> ArtifactStatus:
    if path is None:
        return ArtifactStatus(
            name="docker_endpoint_smoke",
            path=None,
            passed=False,
            summary="missing artifact",
        )
    payload = _load_json(path)
    failed_value = payload.get("failed", [])
    if isinstance(failed_value, int):
        failed_count = failed_value
    elif isinstance(failed_value, list):
        failed_count = len(failed_value)
    else:
        failed_count = 0
    passed = bool(payload.get("passed")) and failed_count == 0
    summary = f"passed={payload.get('passed')}, failed_count={failed_count}"
    return ArtifactStatus(
        name="docker_endpoint_smoke", path=str(path), passed=passed, summary=summary
    )


def _latency_status(path: Path | None) -> ArtifactStatus:
    if path is None:
        return ArtifactStatus(
            name="latency_profile",
            path=None,
            passed=False,
            summary="missing artifact",
        )
    payload = _load_json(path)
    results = payload.get("results", [])
    violated = 0
    for row in results:
        p95_ms = float(row.get("p95_ms", 0.0))
        p95_budget_ms = float(row.get("p95_budget_ms", 0.0))
        error_value = row.get("errors", 0)
        if isinstance(error_value, Real):
            error_count = int(error_value)
        elif isinstance(error_value, list):
            error_count = len(error_value)
        else:
            error_count = 0
        if error_count > 0 or p95_ms > p95_budget_ms:
            violated += 1
    passed = violated == 0 and len(results) > 0
    summary = f"endpoint_count={len(results)}, violations={violated}"
    return ArtifactStatus(name="latency_profile", path=str(path), passed=passed, summary=summary)


def _performance_status(path: Path | None) -> ArtifactStatus:
    if path is None:
        return ArtifactStatus(
            name="performance_load_gate",
            path=None,
            passed=False,
            summary="missing artifact",
        )
    payload = _load_json(path)
    passed = bool(payload.get("overall_passed"))
    profiles = payload.get("profiles", [])
    failed_profiles = [str(p.get("profile_name")) for p in profiles if not p.get("checks_passed")]
    summary = f"overall_passed={passed}, failed_profiles={failed_profiles}"
    return ArtifactStatus(
        name="performance_load_gate", path=str(path), passed=passed, summary=summary
    )


def _failure_recovery_status(path: Path | None) -> ArtifactStatus:
    if path is None:
        return ArtifactStatus(
            name="failure_recovery_gate",
            path=None,
            passed=False,
            summary="missing artifact",
        )
    payload = _load_json(path)
    passed = bool(payload.get("checks_passed"))
    failed_checks = payload.get("failed_checks", [])
    summary = f"checks_passed={passed}, failed_checks={failed_checks}"
    return ArtifactStatus(
        name="failure_recovery_gate", path=str(path), passed=passed, summary=summary
    )


def _load_reconciliation_status(path: Path | None) -> ArtifactStatus:
    if path is None:
        return ArtifactStatus(
            name="bank_day_load_reconciliation",
            path=None,
            passed=False,
            summary="missing artifact",
        )
    payload = _load_json(path)
    run_progress = payload.get("run_progress", {})
    summary = payload.get("summary", {})
    portfolios_evaluated = int(payload.get("portfolio_count_evaluated", 0) or 0)
    run_state = str(run_progress.get("run_state", "UNKNOWN"))
    operator_progress_state = str(run_progress.get("operator_progress_state", "UNKNOWN"))
    complete_portfolios = int(run_progress.get("complete_portfolios", 0) or 0)
    portfolios_ingested = int(run_progress.get("portfolios_ingested", 0) or 0)
    passed = (
        bool(summary.get("all_samples_reconciled"))
        and bool(summary.get("all_position_counts_match_expected"))
        and bool(summary.get("all_transaction_counts_match_expected"))
        and bool(summary.get("all_market_values_match_expected"))
        and portfolios_evaluated > 0
        and run_state == "COMPLETE"
        and operator_progress_state == "COMPLETE"
        and complete_portfolios == portfolios_ingested
    )
    artifact_summary = (
        f"run_state={run_state}, operator_progress_state={operator_progress_state}, "
        f"complete_portfolios={complete_portfolios}/{portfolios_ingested}, "
        f"portfolios_evaluated={portfolios_evaluated}, "
        f"all_samples_reconciled={summary.get('all_samples_reconciled')}"
    )
    return ArtifactStatus(
        name="bank_day_load_reconciliation",
        path=str(path),
        passed=passed,
        summary=artifact_summary,
    )


def _is_artifact_fresh(path: Path, *, max_age_hours: int) -> bool:
    age_seconds = (
        datetime.now(UTC) - datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    ).total_seconds()
    return age_seconds <= (max_age_hours * 3600)


def _freshness_summary(path: Path, *, max_age_hours: int) -> str:
    age_seconds = int(
        (datetime.now(UTC) - datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)).total_seconds()
    )
    return f"age_seconds={age_seconds}, max_age_hours={max_age_hours}"


def _apply_recency_policy(
    statuses: list[ArtifactStatus], *, max_age_hours: int
) -> list[ArtifactStatus]:
    recency_checked: list[ArtifactStatus] = []
    for status in statuses:
        if status.path is None:
            recency_checked.append(status)
            continue
        artifact_path = Path(status.path)
        fresh = _is_artifact_fresh(artifact_path, max_age_hours=max_age_hours)
        recency_checked.append(
            ArtifactStatus(
                name=status.name,
                path=status.path,
                passed=status.passed and fresh,
                summary=(
                    f"{status.summary}; "
                    f"{_freshness_summary(artifact_path, max_age_hours=max_age_hours)}; "
                    f"fresh={fresh}"
                ),
            )
        )
    return recency_checked


def _write_pack(
    output_dir: Path, statuses: list[ArtifactStatus], require_all: bool
) -> tuple[Path, Path, bool]:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    overall_passed = all(item.passed for item in statuses)
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "require_all": require_all,
        "overall_passed": overall_passed,
        "artifacts": [
            {
                "name": item.name,
                "path": item.path,
                "passed": item.passed,
                "summary": item.summary,
            }
            for item in statuses
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}-institutional-signoff-pack.json"
    md_path = output_dir / f"{run_id}-institutional-signoff-pack.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# Institutional Sign-Off Pack {run_id}",
        "",
        f"- Overall passed: {overall_passed}",
        f"- Require all artifacts: {require_all}",
        "",
        "| Artifact | Passed | Summary | Path |",
        "|---|---|---|---|",
    ]
    for item in statuses:
        lines.append(
            f"| {item.name} | {'yes' if item.passed else 'no'} | "
            f"{item.summary} | {item.path or 'missing'} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path, overall_passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate institutional sign-off pack from latest artifacts."
    )
    parser.add_argument("--artifact-dir", default="output/task-runs")
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help="Maximum allowed artifact age for recency policy.",
    )
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    statuses = [
        _docker_smoke_status(_latest_artifact(artifact_dir, "*-docker-endpoint-smoke.json")),
        _latency_status(_latest_artifact(artifact_dir, "*-latency-profile.json")),
        _performance_status(_latest_artifact(artifact_dir, "*-performance-load-gate.json")),
        _failure_recovery_status(_latest_artifact(artifact_dir, "*-failure-recovery-gate.json")),
        _load_reconciliation_status(
            _latest_artifact(artifact_dir, "*-bank-day-load-reconciliation.json")
        ),
    ]
    statuses = _apply_recency_policy(statuses, max_age_hours=args.max_age_hours)
    json_path, md_path, overall_passed = _write_pack(
        output_dir=output_dir,
        statuses=statuses,
        require_all=args.require_all,
    )
    print(f"Wrote sign-off JSON report: {json_path}")
    print(f"Wrote sign-off Markdown report: {md_path}")

    if args.require_all and not overall_passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
