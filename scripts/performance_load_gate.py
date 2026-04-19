"""Deterministic load-profile gate for lotus-core institutional readiness.

Runs three deterministic profiles against ingestion/query services:
1. steady_state
2. burst
3. replay_storm

Writes JSON/Markdown artifacts and optionally enforces profile thresholds.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

try:
    from scripts.ci_service_sets import PERFORMANCE_GATE_SERVICES
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from ci_service_sets import PERFORMANCE_GATE_SERVICES


@dataclass(slots=True)
class ProfileResult:
    profile_name: str
    started_at: str
    ended_at: str
    duration_seconds: float
    records_submitted: int
    batches_submitted: int
    throughput_records_per_second: float
    baseline_backlog_jobs: int
    backlog_jobs_after_profile: int
    backlog_jobs_growth_during_profile: int
    baseline_backlog_age_seconds: float
    backlog_age_seconds_after_profile: float
    backlog_age_increase_seconds: float
    baseline_dlq_events_in_window: int
    dlq_events_in_window_after_profile: int
    dlq_events_added_during_profile: int
    dlq_pressure_ratio_added: float
    baseline_replay_pressure_ratio: float
    replay_pressure_ratio_after_profile: float
    replay_pressure_ratio_increase: float
    drain_seconds_to_zero_backlog: float | None
    checks_passed: bool
    failed_checks: list[str]


def _run(cmd: list[str], cwd: Path) -> None:
    completed = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def _non_negative_delta(current: float, baseline: float) -> float:
    return max(current - baseline, 0.0)


def _non_negative_delta_int(current: int, baseline: int) -> int:
    return max(current - baseline, 0)


def _compose_up(*, repo_root: Path, compose_file: str, build: bool) -> None:
    cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
    if build:
        cmd.append("--build")
    cmd.extend(PERFORMANCE_GATE_SERVICES)
    _run(cmd, cwd=repo_root)


def _wait_ready(
    *,
    ingestion_base_url: str,
    event_replay_base_url: str,
    query_base_url: str,
    timeout_seconds: int,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            ing = requests.get(f"{ingestion_base_url}/health/ready", timeout=5)
            replay = requests.get(f"{event_replay_base_url}/health/ready", timeout=5)
            qry = requests.get(f"{query_base_url}/health/ready", timeout=5)
            if ing.status_code == 200 and replay.status_code == 200 and qry.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("Services did not become ready before timeout.")


def _build_transaction_batch(
    *, portfolio_id: str, batch_size: int, seed: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_ts = "2026-03-01T09:00:00Z"
    for index in range(batch_size):
        txn_suffix = f"{seed}-{index:04d}"
        rows.append(
            {
                "transaction_id": f"TX_{txn_suffix}",
                "portfolio_id": portfolio_id,
                "instrument_id": f"INSTR_{index % 20:03d}",
                "security_id": f"SEC_{index % 20:03d}",
                "transaction_date": base_ts,
                "transaction_type": "BUY",
                "quantity": "10",
                "price": "100.00",
                "gross_transaction_amount": "1000.00",
                "trade_currency": "USD",
                "currency": "USD",
            }
        )
    return rows


def _ingest_transactions(
    *,
    ingestion_base_url: str,
    portfolio_id: str,
    batches: int,
    batch_size: int,
    sleep_seconds_between_batches: float,
) -> tuple[int, int]:
    total_records = 0
    total_batches = 0
    for batch_number in range(batches):
        seed = f"{uuid4().hex[:8]}-{batch_number:03d}"
        payload = {
            "transactions": _build_transaction_batch(
                portfolio_id=portfolio_id,
                batch_size=batch_size,
                seed=seed,
            )
        }
        response = requests.post(
            f"{ingestion_base_url}/ingest/transactions",
            json=payload,
            timeout=30,
        )
        if response.status_code != 202:
            raise RuntimeError(
                "Transaction ingestion failed with "
                f"status={response.status_code}: {response.text[:300]}"
            )
        total_records += batch_size
        total_batches += 1
        if sleep_seconds_between_batches > 0:
            time.sleep(sleep_seconds_between_batches)
    return total_records, total_batches


def _trigger_replay_storm(
    *,
    ingestion_base_url: str,
    transaction_ids: list[str],
    bursts: int,
    burst_size: int,
) -> None:
    if not transaction_ids:
        return
    for burst in range(bursts):
        start = (burst * burst_size) % len(transaction_ids)
        selected = transaction_ids[start : start + burst_size]
        if not selected:
            selected = transaction_ids[:burst_size]
        response = requests.post(
            f"{ingestion_base_url}/reprocess/transactions",
            json={"transaction_ids": selected},
            timeout=30,
        )
        if response.status_code not in {202, 409}:
            raise RuntimeError(
                f"Replay request failed with status={response.status_code}: {response.text[:300]}"
            )


def _get_health_snapshot(*, event_replay_base_url: str, ops_token: str) -> dict[str, Any]:
    headers = {"X-Lotus-Ops-Token": ops_token}
    summary = requests.get(
        f"{event_replay_base_url}/ingestion/health/summary",
        headers=headers,
        timeout=20,
    )
    slo = requests.get(
        f"{event_replay_base_url}/ingestion/health/slo?lookback_minutes=60",
        headers=headers,
        timeout=20,
    )
    error_budget = requests.get(
        f"{event_replay_base_url}/ingestion/health/error-budget?lookback_minutes=60",
        headers=headers,
        timeout=20,
    )
    for response in (summary, slo, error_budget):
        if response.status_code != 200:
            raise RuntimeError(
                f"Health endpoint failed status={response.status_code}: {response.text[:200]}"
            )
    return {
        "summary": summary.json(),
        "slo": slo.json(),
        "error_budget": error_budget.json(),
    }


def _wait_drain_to_target_backlog(
    *,
    event_replay_base_url: str,
    ops_token: str,
    target_backlog_jobs: int,
    timeout_seconds: int,
) -> float | None:
    headers = {"X-Lotus-Ops-Token": ops_token}
    started = time.time()
    deadline = started + timeout_seconds
    while time.time() < deadline:
        response = requests.get(
            f"{event_replay_base_url}/ingestion/health/summary",
            headers=headers,
            timeout=20,
        )
        if response.status_code == 200:
            backlog_jobs = int(response.json().get("backlog_jobs", 0))
            if backlog_jobs <= target_backlog_jobs:
                return round(time.time() - started, 3)
        time.sleep(2)
    return None


def _resolve_drain_timeout_seconds(
    *, configured_timeout: int, max_drain_seconds: float | None
) -> int:
    if max_drain_seconds is None:
        return configured_timeout
    return max(configured_timeout, int(max_drain_seconds) + 60)


def _evaluate_profile(
    *,
    profile_name: str,
    records_submitted: int,
    batches_submitted: int,
    started_at: float,
    ended_at: float,
    baseline_health: dict[str, Any],
    health: dict[str, Any],
    drain_seconds: float | None,
    thresholds: dict[str, float],
) -> ProfileResult:
    duration = max(ended_at - started_at, 0.001)
    throughput = records_submitted / duration
    baseline_summary = baseline_health["summary"]
    baseline_slo = baseline_health["slo"]
    baseline_error_budget = baseline_health["error_budget"]
    summary = health["summary"]
    slo = health["slo"]
    error_budget = health["error_budget"]
    baseline_backlog_jobs = int(baseline_summary.get("backlog_jobs", 0))
    backlog_jobs = int(summary.get("backlog_jobs", 0))
    backlog_jobs_growth = _non_negative_delta_int(backlog_jobs, baseline_backlog_jobs)
    baseline_backlog_age = float(baseline_slo.get("backlog_age_seconds", 0.0))
    backlog_age = float(slo.get("backlog_age_seconds", 0.0))
    backlog_age_increase = _non_negative_delta(backlog_age, baseline_backlog_age)
    baseline_dlq_events = int(baseline_error_budget.get("dlq_events_in_window", 0))
    dlq_events = int(error_budget.get("dlq_events_in_window", 0))
    dlq_events_added = _non_negative_delta_int(dlq_events, baseline_dlq_events)
    dlq_budget_events = max(int(error_budget.get("dlq_budget_events_per_window", 1)), 1)
    dlq_pressure_added = dlq_events_added / dlq_budget_events
    baseline_replay_pressure = float(
        baseline_error_budget.get("replay_backlog_pressure_ratio", 0.0)
    )
    replay_pressure = float(error_budget.get("replay_backlog_pressure_ratio", 0.0))
    replay_pressure_increase = _non_negative_delta(replay_pressure, baseline_replay_pressure)

    failed_checks: list[str] = []
    if throughput < thresholds["min_throughput_rps"]:
        failed_checks.append(
            f"throughput {throughput:.2f} < min {thresholds['min_throughput_rps']:.2f}"
        )
    if backlog_age_increase > thresholds["max_backlog_age_increase_seconds"]:
        failed_checks.append(
            "backlog_age_increase "
            f"{backlog_age_increase:.2f} > max {thresholds['max_backlog_age_increase_seconds']:.2f}"
        )
    if dlq_pressure_added > thresholds["max_dlq_pressure_ratio_added"]:
        failed_checks.append(
            "dlq_pressure_added "
            f"{dlq_pressure_added:.4f} > max {thresholds['max_dlq_pressure_ratio_added']:.4f}"
        )
    if replay_pressure_increase > thresholds["max_replay_pressure_ratio_increase"]:
        failed_checks.append(
            "replay_pressure_increase "
            f"{replay_pressure_increase:.4f} > max "
            f"{thresholds['max_replay_pressure_ratio_increase']:.4f}"
        )
    max_drain = thresholds.get("max_drain_seconds")
    if max_drain is not None and (drain_seconds is None or drain_seconds > max_drain):
        failed_checks.append(
            "drain_seconds "
            f"{drain_seconds if drain_seconds is not None else 'timeout'} "
            f"> max {max_drain:.2f}"
        )

    return ProfileResult(
        profile_name=profile_name,
        started_at=datetime.fromtimestamp(started_at, tz=UTC).isoformat(),
        ended_at=datetime.fromtimestamp(ended_at, tz=UTC).isoformat(),
        duration_seconds=round(duration, 3),
        records_submitted=records_submitted,
        batches_submitted=batches_submitted,
        throughput_records_per_second=round(throughput, 3),
        baseline_backlog_jobs=baseline_backlog_jobs,
        backlog_jobs_after_profile=backlog_jobs,
        backlog_jobs_growth_during_profile=backlog_jobs_growth,
        baseline_backlog_age_seconds=round(baseline_backlog_age, 3),
        backlog_age_seconds_after_profile=round(backlog_age, 3),
        backlog_age_increase_seconds=round(backlog_age_increase, 3),
        baseline_dlq_events_in_window=baseline_dlq_events,
        dlq_events_in_window_after_profile=dlq_events,
        dlq_events_added_during_profile=dlq_events_added,
        dlq_pressure_ratio_added=round(dlq_pressure_added, 6),
        baseline_replay_pressure_ratio=round(baseline_replay_pressure, 6),
        replay_pressure_ratio_after_profile=round(replay_pressure, 6),
        replay_pressure_ratio_increase=round(replay_pressure_increase, 6),
        drain_seconds_to_zero_backlog=drain_seconds,
        checks_passed=not failed_checks,
        failed_checks=failed_checks,
    )


def _write_report(
    *,
    output_dir: Path,
    run_id: str,
    profile_tier: str,
    results: list[ProfileResult],
    enforce: bool,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    overall_passed = all(item.checks_passed for item in results)
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "profile_tier": profile_tier,
        "enforce": enforce,
        "overall_passed": overall_passed,
        "profiles": [asdict(item) for item in results],
    }
    json_path = output_dir / f"{run_id}-performance-load-gate.json"
    md_path = output_dir / f"{run_id}-performance-load-gate.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# Performance Load Gate {run_id}",
        "",
        f"- Overall passed: {overall_passed}",
        f"- Profile tier: {profile_tier}",
        f"- Enforce mode: {enforce}",
        "",
        (
            "| Profile | Passed | Throughput rps | Backlog age increase sec | "
            "DLQ added ratio | Replay pressure increase | Drain sec |"
        ),
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            (
                "| {profile} | {passed} | {throughput:.3f} | "
                "{backlog_age:.3f} | {dlq:.6f} | {replay:.6f} | {drain} |"
            ).format(
                profile=item.profile_name,
                passed="yes" if item.checks_passed else "no",
                throughput=item.throughput_records_per_second,
                backlog_age=item.backlog_age_increase_seconds,
                dlq=item.dlq_pressure_ratio_added,
                replay=item.replay_pressure_ratio_increase,
                drain=(
                    f"{item.drain_seconds_to_zero_backlog:.3f}"
                    if item.drain_seconds_to_zero_backlog is not None
                    else "timeout"
                ),
            )
        )
        if item.failed_checks:
            lines.append("")
            lines.append(f"Failure details ({item.profile_name}):")
            for check in item.failed_checks:
                lines.append(f"- {check}")
            lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic performance load gate.")
    parser.add_argument("--repo-root", default=".", help="Path to lotus-core repository root.")
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument(
        "--ingestion-base-url", default=os.getenv("E2E_INGESTION_URL", "http://localhost:8200")
    )
    parser.add_argument(
        "--query-base-url", default=os.getenv("E2E_QUERY_URL", "http://localhost:8201")
    )
    parser.add_argument(
        "--event-replay-base-url",
        default=os.getenv("E2E_EVENT_REPLAY_URL", "http://localhost:8209"),
    )
    parser.add_argument("--ops-token", default="lotus-core-ops-local")
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--ready-timeout-seconds", type=int, default=240)
    parser.add_argument("--drain-timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--profile-tier",
        choices=("fast", "full"),
        default="full",
        help="fast: PR-friendly quick gate, full: institutional load profile gate.",
    )
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not args.skip_compose:
        _compose_up(repo_root=repo_root, compose_file=args.compose_file, build=args.build)
    _wait_ready(
        ingestion_base_url=args.ingestion_base_url,
        event_replay_base_url=args.event_replay_base_url,
        query_base_url=args.query_base_url,
        timeout_seconds=args.ready_timeout_seconds,
    )

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    portfolio_id = f"PERF_LOAD_{run_id}"
    all_results: list[ProfileResult] = []
    if args.profile_tier == "fast":
        profiles = [
            {
                "name": "steady_state",
                "batches": 2,
                "batch_size": 20,
                "sleep_seconds": 0.2,
                "wait_for_drain": False,
                "thresholds": {
                    "min_throughput_rps": 5.0,
                    "max_backlog_age_increase_seconds": 1800.0,
                    "max_dlq_pressure_ratio_added": 5.0,
                    "max_replay_pressure_ratio_increase": 5.0,
                    "max_drain_seconds": None,
                },
            },
            {
                "name": "burst",
                "batches": 3,
                "batch_size": 40,
                "sleep_seconds": 0.0,
                "wait_for_drain": False,
                "thresholds": {
                    "min_throughput_rps": 10.0,
                    "max_backlog_age_increase_seconds": 2400.0,
                    "max_dlq_pressure_ratio_added": 5.0,
                    "max_replay_pressure_ratio_increase": 5.0,
                    "max_drain_seconds": None,
                },
            },
        ]
    else:
        profiles = [
            {
                "name": "steady_state",
                "batches": 5,
                "batch_size": 40,
                "sleep_seconds": 0.5,
                "wait_for_drain": False,
                "thresholds": {
                    "min_throughput_rps": 10.0,
                    "max_backlog_age_increase_seconds": 1200.0,
                    "max_dlq_pressure_ratio_added": 5.0,
                    "max_replay_pressure_ratio_increase": 5.0,
                    "max_drain_seconds": None,
                },
            },
            {
                "name": "burst",
                "batches": 8,
                "batch_size": 80,
                "sleep_seconds": 0.0,
                "wait_for_drain": False,
                "thresholds": {
                    "min_throughput_rps": 20.0,
                    "max_backlog_age_increase_seconds": 1800.0,
                    "max_dlq_pressure_ratio_added": 10.0,
                    "max_replay_pressure_ratio_increase": 5.0,
                    "max_drain_seconds": None,
                },
            },
        ]

    for profile in profiles:
        baseline_health = _get_health_snapshot(
            event_replay_base_url=args.event_replay_base_url,
            ops_token=args.ops_token,
        )
        baseline_backlog = 0
        if profile["wait_for_drain"]:
            baseline_backlog = int(baseline_health["summary"].get("backlog_jobs", 0))
        started = time.time()
        records_submitted, batches_submitted = _ingest_transactions(
            ingestion_base_url=args.ingestion_base_url,
            portfolio_id=portfolio_id,
            batches=profile["batches"],
            batch_size=profile["batch_size"],
            sleep_seconds_between_batches=profile["sleep_seconds"],
        )
        ended = time.time()
        health = _get_health_snapshot(
            event_replay_base_url=args.event_replay_base_url,
            ops_token=args.ops_token,
        )
        drain_seconds: float | None = None
        if profile["wait_for_drain"]:
            drain_timeout_seconds = _resolve_drain_timeout_seconds(
                configured_timeout=args.drain_timeout_seconds,
                max_drain_seconds=profile["thresholds"].get("max_drain_seconds"),
            )
            drain_seconds = _wait_drain_to_target_backlog(
                event_replay_base_url=args.event_replay_base_url,
                ops_token=args.ops_token,
                target_backlog_jobs=max(baseline_backlog + 1, 0),
                timeout_seconds=drain_timeout_seconds,
            )
        all_results.append(
            _evaluate_profile(
                profile_name=profile["name"],
                records_submitted=records_submitted,
                batches_submitted=batches_submitted,
                started_at=started,
                ended_at=ended,
                baseline_health=baseline_health,
                health=health,
                drain_seconds=drain_seconds,
                thresholds=profile["thresholds"],
            )
        )

    replay_baseline_health = _get_health_snapshot(
        event_replay_base_url=args.event_replay_base_url,
        ops_token=args.ops_token,
    )
    replay_baseline_backlog = 0
    replay_wait_for_drain = False
    if replay_wait_for_drain:
        replay_baseline_backlog = int(replay_baseline_health["summary"].get("backlog_jobs", 0))
    replay_started = time.time()
    replay_source_transactions = _build_transaction_batch(
        portfolio_id=portfolio_id,
        batch_size=120,
        seed=f"REPLAY-{uuid4().hex[:8]}",
    )
    replay_ids = [row["transaction_id"] for row in replay_source_transactions]
    response = requests.post(
        f"{args.ingestion_base_url}/ingest/transactions",
        json={"transactions": replay_source_transactions},
        timeout=30,
    )
    if response.status_code != 202:
        raise RuntimeError(
            f"Replay source ingestion failed status={response.status_code}: {response.text[:300]}"
        )
    replay_bursts = 4 if args.profile_tier == "fast" else 12
    replay_burst_size = 15 if args.profile_tier == "fast" else 30
    _trigger_replay_storm(
        ingestion_base_url=args.ingestion_base_url,
        transaction_ids=replay_ids,
        bursts=replay_bursts,
        burst_size=replay_burst_size,
    )
    replay_ended = time.time()
    replay_health = _get_health_snapshot(
        event_replay_base_url=args.event_replay_base_url,
        ops_token=args.ops_token,
    )
    replay_drain_seconds: float | None = None
    if replay_wait_for_drain:
        replay_max_drain_seconds = 1200.0 if args.profile_tier == "full" else None
        replay_drain_timeout_seconds = _resolve_drain_timeout_seconds(
            configured_timeout=args.drain_timeout_seconds,
            max_drain_seconds=replay_max_drain_seconds,
        )
        replay_drain_seconds = _wait_drain_to_target_backlog(
            event_replay_base_url=args.event_replay_base_url,
            ops_token=args.ops_token,
            target_backlog_jobs=max(replay_baseline_backlog + 1, 0),
            timeout_seconds=replay_drain_timeout_seconds,
        )
    all_results.append(
        _evaluate_profile(
            profile_name="replay_storm",
            records_submitted=120,
            batches_submitted=1 + replay_bursts,
            started_at=replay_started,
            ended_at=replay_ended,
            baseline_health=replay_baseline_health,
            health=replay_health,
            drain_seconds=replay_drain_seconds,
            thresholds={
                "min_throughput_rps": 8.0 if args.profile_tier == "full" else 4.0,
                "max_backlog_age_increase_seconds": (
                    2400.0 if args.profile_tier == "full" else 3600.0
                ),
                "max_dlq_pressure_ratio_added": 25.0 if args.profile_tier == "full" else 5.0,
                "max_replay_pressure_ratio_increase": 5.0,
                "max_drain_seconds": None,
            },
        )
    )

    json_path, md_path = _write_report(
        output_dir=(repo_root / args.output_dir),
        run_id=run_id,
        profile_tier=args.profile_tier,
        results=all_results,
        enforce=args.enforce,
    )
    print(f"Wrote load gate JSON report: {json_path}")
    print(f"Wrote load gate Markdown report: {md_path}")

    overall_passed = all(item.checks_passed for item in all_results)
    if args.enforce and not overall_passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
