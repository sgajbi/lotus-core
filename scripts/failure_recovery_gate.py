"""Deterministic failure-injection and recovery gate for RFC-066 Slice C.

This gate validates bounded recovery after a controlled worker interruption:
1. Start/verify stack readiness.
2. Inject transaction load.
3. Pause a critical consumer container.
4. Verify backlog growth under interruption.
5. Unpause and verify bounded drain to baseline.
6. Enforce recovery thresholds and publish artifacts.
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


@dataclass(slots=True)
class RecoveryResult:
    run_id: str
    started_at: str
    ended_at: str
    interruption_container: str
    interruption_seconds: int
    baseline_backlog_jobs: int
    peak_backlog_jobs_during_interruption: int
    backlog_growth_jobs: int
    drain_seconds_to_baseline: float | None
    backlog_age_seconds_after_recovery: float
    dlq_pressure_ratio_after_recovery: float
    replay_pressure_ratio_after_recovery: float
    checks_passed: bool
    failed_checks: list[str]


def _run(cmd: list[str], cwd: Path) -> None:
    _run_capture(cmd, cwd=cwd)


def _run_capture(cmd: list[str], cwd: Path) -> str:
    completed = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed.stdout


def _compose_up(*, repo_root: Path, compose_file: str, build: bool) -> None:
    cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
    if build:
        cmd.append("--build")
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
        suffix = f"{seed}-{index:04d}"
        rows.append(
            {
                "transaction_id": f"TX_FAIL_{suffix}",
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
) -> int:
    total_records = 0
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
        if sleep_seconds_between_batches > 0:
            time.sleep(sleep_seconds_between_batches)
    return total_records


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


def _get_backlog_jobs(*, event_replay_base_url: str, ops_token: str) -> int:
    headers = {"X-Lotus-Ops-Token": ops_token}
    response = requests.get(
        f"{event_replay_base_url}/ingestion/health/summary",
        headers=headers,
        timeout=20,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Backlog summary endpoint failed status={response.status_code}: {response.text[:200]}"
        )
    return int(response.json().get("backlog_jobs", 0))


def _resolve_interruption_container(
    *, repo_root: Path, compose_file: str, interruption_container: str
) -> str:
    """
    Resolve interruption target using docker compose service lookup first.
    Falls back to the original argument to preserve manual container-name usage.
    """
    target = interruption_container.strip()
    if not target:
        raise ValueError("interruption container cannot be empty")
    try:
        container_id = _run_capture(
            ["docker", "compose", "-f", compose_file, "ps", "-q", target],
            cwd=repo_root,
        ).strip()
    except RuntimeError:
        container_id = ""
    return container_id or target


def _pause_container(container_name: str, repo_root: Path) -> None:
    _run(["docker", "pause", container_name], cwd=repo_root)


def _unpause_container(container_name: str, repo_root: Path) -> None:
    _run(["docker", "unpause", container_name], cwd=repo_root)


def _wait_drain_to_target_backlog(
    *,
    event_replay_base_url: str,
    ops_token: str,
    target_backlog_jobs: int,
    timeout_seconds: int,
) -> float | None:
    started = time.time()
    deadline = started + timeout_seconds
    while time.time() < deadline:
        backlog_jobs = _get_backlog_jobs(
            event_replay_base_url=event_replay_base_url,
            ops_token=ops_token,
        )
        if backlog_jobs <= target_backlog_jobs:
            return round(time.time() - started, 3)
        time.sleep(2)
    return None


def _write_report(*, output_dir: Path, result: RecoveryResult) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    drain_to_baseline = (
        result.drain_seconds_to_baseline
        if result.drain_seconds_to_baseline is not None
        else "timeout"
    )
    json_path = output_dir / f"{result.run_id}-failure-recovery-gate.json"
    md_path = output_dir / f"{result.run_id}-failure-recovery-gate.md"
    json_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")

    lines = [
        f"# Failure Recovery Gate {result.run_id}",
        "",
        f"- Overall passed: {result.checks_passed}",
        f"- Interrupted container: `{result.interruption_container}`",
        f"- Interruption duration (s): {result.interruption_seconds}",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| baseline_backlog_jobs | {result.baseline_backlog_jobs} |",
        (
            "| peak_backlog_jobs_during_interruption | "
            f"{result.peak_backlog_jobs_during_interruption} |"
        ),
        f"| backlog_growth_jobs | {result.backlog_growth_jobs} |",
        (
            "| drain_seconds_to_baseline | "
            f"{drain_to_baseline} |"
        ),
        f"| backlog_age_seconds_after_recovery | {result.backlog_age_seconds_after_recovery:.3f} |",
        f"| dlq_pressure_ratio_after_recovery | {result.dlq_pressure_ratio_after_recovery:.6f} |",
        (
            "| replay_pressure_ratio_after_recovery | "
            f"{result.replay_pressure_ratio_after_recovery:.6f} |"
        ),
    ]
    if result.failed_checks:
        lines.extend(["", "## Failed checks"])
        for check in result.failed_checks:
            lines.append(f"- {check}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic failure-injection recovery gate."
    )
    parser.add_argument("--repo-root", default=".", help="Path to lotus-core repository root.")
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument(
        "--ingestion-base-url", default=os.getenv("E2E_INGESTION_URL", "http://localhost:8200")
    )
    parser.add_argument(
        "--query-base-url", default=os.getenv("E2E_QUERY_URL", "http://localhost:8201")
    )
    parser.add_argument(
        "--event-replay-base-url", default=os.getenv("E2E_EVENT_REPLAY_URL", "http://localhost:8209")
    )
    parser.add_argument("--ops-token", default="lotus-core-ops-local")
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--ready-timeout-seconds", type=int, default=240)
    parser.add_argument("--interruption-seconds", type=int, default=25)
    parser.add_argument("--recovery-timeout-seconds", type=int, default=480)
    parser.add_argument("--interruption-container", default="persistence_service")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if not args.skip_compose:
        _compose_up(repo_root=repo_root, compose_file=args.compose_file, build=args.build)
    _wait_ready(
        ingestion_base_url=args.ingestion_base_url,
        event_replay_base_url=args.event_replay_base_url,
        query_base_url=args.query_base_url,
        timeout_seconds=args.ready_timeout_seconds,
    )

    started = time.time()
    baseline_backlog_jobs = _get_backlog_jobs(
        event_replay_base_url=args.event_replay_base_url,
        ops_token=args.ops_token,
    )
    portfolio_id = f"FAIL_RECOVERY_{run_id}"

    _ingest_transactions(
        ingestion_base_url=args.ingestion_base_url,
        portfolio_id=portfolio_id,
        batches=2,
        batch_size=40,
        sleep_seconds_between_batches=0.1,
    )

    interruption_target = _resolve_interruption_container(
        repo_root=repo_root,
        compose_file=args.compose_file,
        interruption_container=args.interruption_container,
    )
    _pause_container(interruption_target, repo_root=repo_root)
    peak_backlog = baseline_backlog_jobs
    try:
        interruption_deadline = time.time() + args.interruption_seconds
        while time.time() < interruption_deadline:
            _ingest_transactions(
                ingestion_base_url=args.ingestion_base_url,
                portfolio_id=portfolio_id,
                batches=1,
                batch_size=25,
                sleep_seconds_between_batches=0.0,
            )
            current_backlog = _get_backlog_jobs(
                event_replay_base_url=args.event_replay_base_url,
                ops_token=args.ops_token,
            )
            peak_backlog = max(peak_backlog, current_backlog)
            time.sleep(1)
    finally:
        _unpause_container(interruption_target, repo_root=repo_root)

    drain_seconds = _wait_drain_to_target_backlog(
        event_replay_base_url=args.event_replay_base_url,
        ops_token=args.ops_token,
        target_backlog_jobs=max(baseline_backlog_jobs + 1, 0),
        timeout_seconds=args.recovery_timeout_seconds,
    )
    recovery_health = _get_health_snapshot(
        event_replay_base_url=args.event_replay_base_url,
        ops_token=args.ops_token,
    )
    ended = time.time()

    backlog_growth = max(0, peak_backlog - baseline_backlog_jobs)
    backlog_age = float(recovery_health["slo"].get("backlog_age_seconds", 0.0))
    dlq_pressure = float(recovery_health["error_budget"].get("dlq_pressure_ratio", 0.0))
    replay_pressure = float(
        recovery_health["error_budget"].get("replay_backlog_pressure_ratio", 0.0)
    )

    failed_checks: list[str] = []
    if backlog_growth < 2:
        failed_checks.append("backlog growth during interruption was too small (< 2 jobs)")
    if drain_seconds is not None and drain_seconds > 420:
        failed_checks.append(f"recovery drain {drain_seconds:.2f}s exceeded max 420.00s")
    if drain_seconds is None and backlog_age > 1200:
        failed_checks.append(
            "recovery drain timeout with elevated backlog age (>1200s) "
            "indicates incomplete recovery"
        )
    if backlog_age > 1800:
        failed_checks.append(f"backlog age after recovery {backlog_age:.2f}s exceeded 1800s")
    if dlq_pressure > 5.0:
        failed_checks.append(f"DLQ pressure after recovery {dlq_pressure:.4f} exceeded 5.0000")
    if replay_pressure > 5.0:
        failed_checks.append(
            f"Replay pressure after recovery {replay_pressure:.4f} exceeded 5.0000"
        )

    result = RecoveryResult(
        run_id=run_id,
        started_at=datetime.fromtimestamp(started, tz=UTC).isoformat(),
        ended_at=datetime.fromtimestamp(ended, tz=UTC).isoformat(),
        interruption_container=interruption_target,
        interruption_seconds=args.interruption_seconds,
        baseline_backlog_jobs=baseline_backlog_jobs,
        peak_backlog_jobs_during_interruption=peak_backlog,
        backlog_growth_jobs=backlog_growth,
        drain_seconds_to_baseline=drain_seconds,
        backlog_age_seconds_after_recovery=round(backlog_age, 3),
        dlq_pressure_ratio_after_recovery=round(dlq_pressure, 6),
        replay_pressure_ratio_after_recovery=round(replay_pressure, 6),
        checks_passed=not failed_checks,
        failed_checks=failed_checks,
    )
    json_path, md_path = _write_report(output_dir=(repo_root / args.output_dir), result=result)
    print(f"Wrote failure recovery JSON report: {json_path}")
    print(f"Wrote failure recovery Markdown report: {md_path}")

    if args.enforce and not result.checks_passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
