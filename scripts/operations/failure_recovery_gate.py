"""Prove bounded recovery of the unified transaction-processing runtime.

The gate pauses the combined cost, cashflow, and position consumer, submits valid
transactions, proves committed Kafka lag grows, resumes the consumer, and then
requires exact persistence and zero-lag recovery.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol, cast

import requests  # type: ignore[import-untyped]
from portfolio_common.config import (
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)
from sqlalchemy import Engine, create_engine

if TYPE_CHECKING:
    from tests.test_support.managed_compose_run import ManagedComposeRun

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.operations.transaction_processing_cutover_offsets import KafkaOffsetStore
    from scripts.operations.transaction_processing_load_support import (
        TransactionProcessingCounts,
        ingest_transactions,
        seed_load_context,
        transaction_processing_counts,
        wait_for_database_count,
    )
    from scripts.quality.ci_service_sets import (
        FAILURE_RECOVERY_GATE_SERVICES as _FAILURE_RECOVERY_GATE_SERVICES,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from ci_service_sets import (  # type: ignore[no-redef]
        FAILURE_RECOVERY_GATE_SERVICES as _FAILURE_RECOVERY_GATE_SERVICES,
    )
    from transaction_processing_cutover_offsets import KafkaOffsetStore
    from transaction_processing_load_support import (
        TransactionProcessingCounts,
        ingest_transactions,
        seed_load_context,
        transaction_processing_counts,
        wait_for_database_count,
    )

TRANSACTION_PROCESSING_GROUP = "portfolio_transaction_processing_group"
TRANSACTION_REPLAY_GROUP = "portfolio_transaction_replay_request_group"


class RuntimeConnectionEndpoints(Protocol):
    """Generated host endpoints required by the failure-recovery driver."""

    host_database_url: str
    kafka_bootstrap_servers: str


def _resolve_runtime_connections(
    *,
    requested_host_database_url: str | None,
    requested_kafka_bootstrap_servers: str | None,
    endpoints: RuntimeConnectionEndpoints,
) -> tuple[str, str]:
    """Prefer explicit operator endpoints and otherwise use the isolated test runtime."""

    return (
        requested_host_database_url or endpoints.host_database_url,
        requested_kafka_bootstrap_servers or endpoints.kafka_bootstrap_servers,
    )


class RecoveryMode(StrEnum):
    FULLY_DRAINED = "FULLY_DRAINED"
    FAILED_RECOVERY = "FAILED_RECOVERY"


class RecoveryComparison(StrEnum):
    """Comparison applied to one observed recovery field."""

    EQUALS = "equals"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


@dataclass(frozen=True, slots=True)
class RecoveryFieldEvidence:
    """Final value, target, and change time for one recovery predicate."""

    field: str
    actual: int
    expected: int
    comparison: str
    satisfied: bool
    last_changed_at: str


@dataclass(frozen=True, slots=True)
class RecoveryPollingEvidence:
    """Field-level state accumulated by bounded recovery polling."""

    poll_count: int
    last_observed_at: str
    fields: tuple[RecoveryFieldEvidence, ...]
    terminal_reason: str | None


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def _recovery_comparison_satisfied(
    *, actual: int, expected: int, comparison: RecoveryComparison
) -> bool:
    """Evaluate one field against its explicit recovery target."""

    match comparison:
        case RecoveryComparison.EQUALS:
            return actual == expected
        case RecoveryComparison.AT_LEAST:
            return actual >= expected
        case RecoveryComparison.AT_MOST:
            return actual <= expected


@dataclass(slots=True)
class RecoveryResult:
    run_id: str
    started_at: str
    ended_at: str
    interruption_service: str
    interruption_container_id: str
    requested_interruption_seconds: int
    actual_interruption_seconds: float
    transaction_topic: str
    consumer_group: str
    records_submitted: int
    source_persistence_seconds: float
    baseline_consumer_lag: int
    peak_consumer_lag_during_interruption: int
    consumer_lag_growth: int
    consumer_lag_after_recovery: int
    baseline_replay_consumer_lag: int
    replay_consumer_lag_after_recovery: int
    transaction_processing_recovery_seconds: float | None
    transaction_count: int
    cost_count: int
    cashflow_count: int
    position_count: int
    processing_claim_count: int
    dlq_events_added_during_recovery: int
    recovery_polling: RecoveryPollingEvidence
    recovery_mode: str
    checks_passed: bool
    failed_checks: list[str]


def _evaluate_recovery_result(
    *,
    records_submitted: int,
    baseline_consumer_lag: int,
    consumer_lag_growth: int,
    consumer_lag_after_recovery: int,
    baseline_replay_consumer_lag: int,
    replay_consumer_lag_after_recovery: int,
    transaction_processing_recovery_seconds: float | None,
    max_recovery_seconds: int,
    counts: TransactionProcessingCounts,
    dlq_events_added_during_recovery: int,
    recovery_terminal_reason: str | None = None,
) -> tuple[RecoveryMode, list[str]]:
    failed_checks: list[str] = []
    if consumer_lag_growth < records_submitted:
        failed_checks.append(
            "transaction consumer lag growth "
            f"{consumer_lag_growth} was below submitted records {records_submitted}"
        )
    if transaction_processing_recovery_seconds is None:
        failed_checks.append("transaction processing did not fully recover before timeout")
    elif transaction_processing_recovery_seconds > max_recovery_seconds:
        failed_checks.append(
            "transaction processing recovery "
            f"{transaction_processing_recovery_seconds:.2f}s exceeded "
            f"{max_recovery_seconds}s"
        )
    if consumer_lag_after_recovery > baseline_consumer_lag:
        failed_checks.append(
            "transaction consumer lag after recovery "
            f"{consumer_lag_after_recovery} exceeded baseline {baseline_consumer_lag}"
        )
    if replay_consumer_lag_after_recovery > baseline_replay_consumer_lag:
        failed_checks.append(
            "transaction replay consumer lag after recovery "
            f"{replay_consumer_lag_after_recovery} exceeded baseline "
            f"{baseline_replay_consumer_lag}"
        )

    exact_counts = {
        "transaction": counts.transaction_count,
        "cost": counts.cost_count,
        "cashflow": counts.cashflow_count,
        "position": counts.position_count,
    }
    for name, actual in exact_counts.items():
        if actual != records_submitted:
            failed_checks.append(
                f"{name} completion count {actual} did not equal submitted {records_submitted}"
            )
    if counts.processing_claim_count < records_submitted:
        failed_checks.append(
            "transaction processing claim count "
            f"{counts.processing_claim_count} was below submitted {records_submitted}"
        )
    if dlq_events_added_during_recovery:
        failed_checks.append(
            f"failure recovery added {dlq_events_added_during_recovery} DLQ events"
        )
    if recovery_terminal_reason:
        failed_checks.append(f"recovery polling stopped early: {recovery_terminal_reason}")
    if failed_checks:
        return RecoveryMode.FAILED_RECOVERY, failed_checks
    return RecoveryMode.FULLY_DRAINED, failed_checks


def _run_capture(cmd: list[str], cwd: Path) -> str:
    completed = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed.stdout


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
            ingestion = requests.get(f"{ingestion_base_url}/health/ready", timeout=5)
            replay = requests.get(f"{event_replay_base_url}/health/ready", timeout=5)
            query = requests.get(f"{query_base_url}/health/ready", timeout=5)
            if (
                ingestion.status_code == 200
                and replay.status_code == 200
                and query.status_code == 200
            ):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("Services did not become ready before timeout.")


def _get_health_snapshot(*, event_replay_base_url: str, ops_token: str) -> dict[str, Any]:
    headers = {"X-Lotus-Ops-Token": ops_token}
    error_budget = requests.get(
        f"{event_replay_base_url}/ingestion/health/error-budget?lookback_minutes=60",
        headers=headers,
        timeout=20,
    )
    if error_budget.status_code != 200:
        raise RuntimeError(
            f"Health endpoint failed status={error_budget.status_code}: {error_budget.text[:200]}"
        )
    return cast(dict[str, Any], error_budget.json())


def _compose_command(
    *, compose_file: str, compose_project_name: str | None, arguments: list[str]
) -> list[str]:
    command = ["docker", "compose"]
    if compose_project_name:
        command.extend(["-p", compose_project_name])
    command.extend(["-f", compose_file, *arguments])
    return command


def _resolve_interruption_container(
    *,
    repo_root: Path,
    compose_file: str,
    compose_project_name: str | None,
    interruption_service: str,
) -> str:
    target = interruption_service.strip()
    if not target:
        raise ValueError("interruption service cannot be empty")
    container_id = _run_capture(
        _compose_command(
            compose_file=compose_file,
            compose_project_name=compose_project_name,
            arguments=["ps", "-q", target],
        ),
        cwd=repo_root,
    ).strip()
    if not container_id:
        raise RuntimeError(f"Compose service is not running: {target}")
    return container_id


def _set_container_pause(*, container_id: str, paused: bool, repo_root: Path) -> None:
    operation = "pause" if paused else "unpause"
    _run_capture(["docker", operation, container_id], cwd=repo_root)


def _consumer_lag(*, store: KafkaOffsetStore, consumer_group: str, transaction_topic: str) -> int:
    snapshot = store.snapshot(group_id=consumer_group, topic=transaction_topic)
    return sum(
        max(partition.high_watermark - max(partition.committed_offset, 0), 0)
        for partition in snapshot.partitions
    )


def _wait_for_lag_growth(
    *,
    store: KafkaOffsetStore,
    consumer_group: str,
    transaction_topic: str,
    baseline_lag: int,
    expected_growth: int,
    timeout_seconds: int,
) -> int:
    peak_lag = baseline_lag
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        current_lag = _consumer_lag(
            store=store,
            consumer_group=consumer_group,
            transaction_topic=transaction_topic,
        )
        peak_lag = max(peak_lag, current_lag)
        if peak_lag - baseline_lag >= expected_growth:
            return peak_lag
        time.sleep(1)
    return peak_lag


def _wait_for_full_recovery(
    *,
    store: KafkaOffsetStore,
    engine: Engine,
    consumer_group: str,
    transaction_topic: str,
    baseline_lag: int,
    portfolio_id: str,
    transaction_id_prefix: str,
    expected_records: int,
    timeout_seconds: int,
    terminal_condition: Callable[[], str | None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    utc_now: Callable[[], datetime] = _utc_now,
) -> tuple[
    float | None,
    TransactionProcessingCounts,
    int,
    RecoveryPollingEvidence,
]:
    started = clock()
    deadline = started + timeout_seconds
    last_values: dict[str, int] = {}
    last_changed_at: dict[str, str] = {}
    poll_count = 0
    while True:
        counts = transaction_processing_counts(
            engine=engine,
            portfolio_id=portfolio_id,
            transaction_id_prefix=transaction_id_prefix,
        )
        consumer_lag = _consumer_lag(
            store=store,
            consumer_group=consumer_group,
            transaction_topic=transaction_topic,
        )
        observed_at = utc_now().isoformat()
        poll_count += 1
        values = {
            "transaction_count": counts.transaction_count,
            "cost_count": counts.cost_count,
            "cashflow_count": counts.cashflow_count,
            "position_count": counts.position_count,
            "processing_claim_count": counts.processing_claim_count,
            "consumer_lag": consumer_lag,
        }
        for field, value in values.items():
            if field not in last_values or last_values[field] != value:
                last_changed_at[field] = observed_at
        last_values = values
        field_targets = (
            ("transaction_count", expected_records, RecoveryComparison.EQUALS),
            ("cost_count", expected_records, RecoveryComparison.EQUALS),
            ("cashflow_count", expected_records, RecoveryComparison.EQUALS),
            ("position_count", expected_records, RecoveryComparison.EQUALS),
            ("processing_claim_count", expected_records, RecoveryComparison.AT_LEAST),
            ("consumer_lag", baseline_lag, RecoveryComparison.AT_MOST),
        )
        fields = tuple(
            RecoveryFieldEvidence(
                field=field,
                actual=values[field],
                expected=expected,
                comparison=comparison.value,
                satisfied=_recovery_comparison_satisfied(
                    actual=values[field],
                    expected=expected,
                    comparison=comparison,
                ),
                last_changed_at=last_changed_at[field],
            )
            for field, expected, comparison in field_targets
        )
        terminal_reason = next(
            (
                f"{field.field} exceeded exact target: "
                f"actual={field.actual} expected={field.expected}"
                for field in fields
                if field.comparison == RecoveryComparison.EQUALS.value
                and field.actual > field.expected
            ),
            None,
        )
        if terminal_reason is None and terminal_condition is not None:
            terminal_reason = terminal_condition()
        evidence = RecoveryPollingEvidence(
            poll_count=poll_count,
            last_observed_at=observed_at,
            fields=fields,
            terminal_reason=terminal_reason,
        )
        if terminal_reason is not None:
            return None, counts, consumer_lag, evidence
        if all(field.satisfied for field in fields):
            return round(clock() - started, 3), counts, consumer_lag, evidence
        if clock() >= deadline:
            return None, counts, consumer_lag, evidence
        sleeper(1)


def _write_report(*, output_dir: Path, result: RecoveryResult) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    recovery_seconds: float | str = (
        result.transaction_processing_recovery_seconds
        if result.transaction_processing_recovery_seconds is not None
        else "timeout"
    )
    json_path = output_dir / f"{result.run_id}-failure-recovery-gate.json"
    markdown_path = output_dir / f"{result.run_id}-failure-recovery-gate.md"
    json_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")

    lines = [
        f"# Failure Recovery Gate {result.run_id}",
        "",
        "- Boundary: unified cost, cashflow, and position transaction processing",
        "- Completion: exact domain persistence, idempotency claims, and committed Kafka lag",
        f"- Overall passed: {result.checks_passed}",
        f"- Recovery mode: `{result.recovery_mode}`",
        f"- Interrupted service: `{result.interruption_service}`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| records_submitted | {result.records_submitted} |",
        f"| source_persistence_seconds | {result.source_persistence_seconds:.3f} |",
        f"| requested_interruption_seconds | {result.requested_interruption_seconds} |",
        f"| actual_interruption_seconds | {result.actual_interruption_seconds:.3f} |",
        f"| baseline_consumer_lag | {result.baseline_consumer_lag} |",
        (
            "| peak_consumer_lag_during_interruption | "
            f"{result.peak_consumer_lag_during_interruption} |"
        ),
        f"| consumer_lag_growth | {result.consumer_lag_growth} |",
        f"| consumer_lag_after_recovery | {result.consumer_lag_after_recovery} |",
        f"| baseline_replay_consumer_lag | {result.baseline_replay_consumer_lag} |",
        (f"| replay_consumer_lag_after_recovery | {result.replay_consumer_lag_after_recovery} |"),
        f"| transaction_processing_recovery_seconds | {recovery_seconds} |",
        f"| transaction_count | {result.transaction_count} |",
        f"| cost_count | {result.cost_count} |",
        f"| cashflow_count | {result.cashflow_count} |",
        f"| position_count | {result.position_count} |",
        f"| processing_claim_count | {result.processing_claim_count} |",
        f"| dlq_events_added_during_recovery | {result.dlq_events_added_during_recovery} |",
        f"| recovery_poll_count | {result.recovery_polling.poll_count} |",
        f"| recovery_terminal_reason | {result.recovery_polling.terminal_reason or ''} |",
    ]
    lines.extend(
        [
            "",
            "## Recovery field evidence",
            "",
            "| Field | Actual | Comparison | Expected | Satisfied | Last changed at |",
            "|---|---:|---|---:|---|---|",
        ]
    )
    lines.extend(
        "| "
        f"{field.field} | {field.actual} | {field.comparison} | {field.expected} | "
        f"{field.satisfied} | {field.last_changed_at} |"
        for field in result.recovery_polling.fields
    )
    if result.failed_checks:
        lines.extend(["", "## Failed checks"])
        lines.extend(f"- {check}" for check in result.failed_checks)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _load_test_runtime_helpers():
    from tests.test_support.docker_stack import wait_for_migration_runner
    from tests.test_support.managed_compose_run import prepare_managed_compose_run

    return wait_for_migration_runner, prepare_managed_compose_run


def _prepare_failure_recovery_managed_run(
    *, args: argparse.Namespace, repo_root: Path
) -> ManagedComposeRun:
    """Prepare the isolated Compose owner for one failure-recovery proof run."""

    _, prepare_managed_compose_run = _load_test_runtime_helpers()
    compose_file = Path(args.compose_file)
    if not compose_file.is_absolute():
        compose_file = repo_root / compose_file
    return prepare_managed_compose_run(
        profile="integration",
        scope="failure-recovery-gate",
        compose_project_name=(
            args.compose_project_name
            or (os.getenv("COMPOSE_PROJECT_NAME") if args.skip_compose else None)
        ),
        compose_file=compose_file,
        services=_FAILURE_RECOVERY_GATE_SERVICES,
        build=args.build,
        log_path=(
            repo_root / args.output_dir / "diagnostics" / "failure-recovery-gate-compose.log"
        ),
        endpoint_urls={
            "E2E_INGESTION_URL": args.ingestion_base_url,
            "E2E_QUERY_URL": args.query_base_url,
            "E2E_EVENT_REPLAY_URL": args.event_replay_base_url,
            "HOST_DATABASE_URL": args.host_database_url,
        },
        allocate_dynamic_ports=not args.skip_compose,
        keep_stack=args.keep_stack_up,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prove unified transaction-processing failure recovery."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument("--compose-project-name", default=None)
    parser.add_argument("--ingestion-base-url", default=None)
    parser.add_argument("--query-base-url", default=None)
    parser.add_argument("--event-replay-base-url", default=None)
    parser.add_argument(
        "--host-database-url",
        default=None,
    )
    parser.add_argument("--kafka-bootstrap-servers", default=None)
    parser.add_argument("--transaction-topic", default=KAFKA_TRANSACTIONS_PERSISTED_TOPIC)
    parser.add_argument("--consumer-group", default=TRANSACTION_PROCESSING_GROUP)
    parser.add_argument(
        "--replay-topic",
        default=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
    )
    parser.add_argument("--replay-consumer-group", default=TRANSACTION_REPLAY_GROUP)
    parser.add_argument("--ops-token", default="lotus-core-ops-local")
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--keep-stack-up", action="store_true")
    parser.add_argument("--ready-timeout-seconds", type=int, default=240)
    parser.add_argument("--interruption-seconds", type=int, default=25)
    parser.add_argument("--backlog-build-timeout-seconds", type=int, default=120)
    parser.add_argument("--recovery-timeout-seconds", type=int, default=480)
    parser.add_argument("--max-recovery-seconds", type=int, default=420)
    parser.add_argument("--batches", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument(
        "--interruption-service",
        "--interruption-container",
        dest="interruption_service",
        default="portfolio_transaction_processing_service",
    )
    parser.add_argument("--enforce", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    run_started_at = datetime.now(UTC)
    run_id = run_started_at.strftime("%Y%m%dT%H%M%SZ")
    business_date = run_started_at.date().isoformat()
    transaction_date = f"{business_date}T09:00:00Z"
    portfolio_id = f"FAIL_RECOVERY_{run_id}"
    security_prefix = f"FAIL_{run_id[-9:-1]}_SEC"
    transaction_seed = f"FAIL-{run_id}"
    transaction_id_prefix = f"TX_{transaction_seed}"

    wait_for_migration_runner, _ = _load_test_runtime_helpers()
    managed_run = _prepare_failure_recovery_managed_run(args=args, repo_root=repo_root)
    runtime = managed_run.runtime
    runtime.export_to(os.environ)

    with ExitStack() as lifecycle:
        if not args.skip_compose:
            lifecycle.enter_context(managed_run)
            wait_for_migration_runner(
                managed_run.compose_file,
                timeout_seconds=args.ready_timeout_seconds,
                runtime=runtime,
            )
        else:
            runtime.port_reservation.release()

        endpoints = runtime.endpoints
        ingestion_base_url = args.ingestion_base_url or endpoints.e2e_ingestion_url
        query_base_url = args.query_base_url or endpoints.e2e_query_url
        event_replay_base_url = args.event_replay_base_url or endpoints.e2e_event_replay_url
        host_database_url, kafka_bootstrap_servers = _resolve_runtime_connections(
            requested_host_database_url=args.host_database_url,
            requested_kafka_bootstrap_servers=args.kafka_bootstrap_servers,
            endpoints=endpoints,
        )
        engine = create_engine(host_database_url, pool_pre_ping=True)
        lifecycle.callback(engine.dispose)
        offset_store = KafkaOffsetStore(
            bootstrap_servers=kafka_bootstrap_servers,
            timeout_seconds=10,
        )
        lifecycle.callback(offset_store.close)
        _wait_ready(
            ingestion_base_url=ingestion_base_url,
            event_replay_base_url=event_replay_base_url,
            query_base_url=query_base_url,
            timeout_seconds=args.ready_timeout_seconds,
        )
        seed_load_context(
            engine=engine,
            ingestion_base_url=ingestion_base_url,
            run_id=run_id,
            portfolio_id=portfolio_id,
            security_prefix=security_prefix,
            business_date=business_date,
            timeout_seconds=args.ready_timeout_seconds,
        )

        baseline_health = _get_health_snapshot(
            event_replay_base_url=event_replay_base_url,
            ops_token=args.ops_token,
        )
        baseline_dlq = int(baseline_health.get("dlq_events_in_window", 0))
        baseline_consumer_lag = _consumer_lag(
            store=offset_store,
            consumer_group=args.consumer_group,
            transaction_topic=args.transaction_topic,
        )
        baseline_replay_consumer_lag = _consumer_lag(
            store=offset_store,
            consumer_group=args.replay_consumer_group,
            transaction_topic=args.replay_topic,
        )
        interruption_container_id = _resolve_interruption_container(
            repo_root=repo_root,
            compose_file=args.compose_file,
            compose_project_name=endpoints.compose_project_name,
            interruption_service=args.interruption_service,
        )

        interruption_started = time.time()
        _set_container_pause(
            container_id=interruption_container_id,
            paused=True,
            repo_root=repo_root,
        )
        try:
            transaction_ids, _ = ingest_transactions(
                ingestion_base_url=ingestion_base_url,
                portfolio_id=portfolio_id,
                batches=args.batches,
                batch_size=args.batch_size,
                sleep_seconds_between_batches=0,
                seed_prefix=transaction_seed,
                security_prefix=security_prefix,
                transaction_date=transaction_date,
            )
            records_submitted = len(transaction_ids)
            source_wait_started = time.time()
            wait_for_database_count(
                engine=engine,
                sql="SELECT count(*) FROM transactions WHERE transaction_id LIKE :pattern",
                params={"pattern": f"{transaction_id_prefix}%"},
                expected=records_submitted,
                label="failure recovery source persistence",
                timeout_seconds=args.ready_timeout_seconds,
            )
            source_persistence_seconds = round(time.time() - source_wait_started, 3)
            peak_consumer_lag = _wait_for_lag_growth(
                store=offset_store,
                consumer_group=args.consumer_group,
                transaction_topic=args.transaction_topic,
                baseline_lag=baseline_consumer_lag,
                expected_growth=records_submitted,
                timeout_seconds=args.backlog_build_timeout_seconds,
            )
            minimum_resume_at = interruption_started + args.interruption_seconds
            if time.time() < minimum_resume_at:
                time.sleep(minimum_resume_at - time.time())
        finally:
            _set_container_pause(
                container_id=interruption_container_id,
                paused=False,
                repo_root=repo_root,
            )
        actual_interruption_seconds = round(time.time() - interruption_started, 3)

        def dlq_terminal_condition() -> str | None:
            health = _get_health_snapshot(
                event_replay_base_url=event_replay_base_url,
                ops_token=args.ops_token,
            )
            current_dlq = int(health.get("dlq_events_in_window", 0))
            if current_dlq <= baseline_dlq:
                return None
            return f"DLQ events increased: baseline={baseline_dlq} current={current_dlq}"

        recovery_seconds, counts, lag_after_recovery, recovery_polling = _wait_for_full_recovery(
            store=offset_store,
            engine=engine,
            consumer_group=args.consumer_group,
            transaction_topic=args.transaction_topic,
            baseline_lag=baseline_consumer_lag,
            portfolio_id=portfolio_id,
            transaction_id_prefix=transaction_id_prefix,
            expected_records=records_submitted,
            timeout_seconds=args.recovery_timeout_seconds,
            terminal_condition=dlq_terminal_condition,
        )
        recovery_health = _get_health_snapshot(
            event_replay_base_url=event_replay_base_url,
            ops_token=args.ops_token,
        )
        recovery_dlq = int(recovery_health.get("dlq_events_in_window", 0))
        dlq_events_added = max(recovery_dlq - baseline_dlq, 0)
        replay_consumer_lag_after_recovery = _consumer_lag(
            store=offset_store,
            consumer_group=args.replay_consumer_group,
            transaction_topic=args.replay_topic,
        )
        consumer_lag_growth = max(peak_consumer_lag - baseline_consumer_lag, 0)
        recovery_mode, failed_checks = _evaluate_recovery_result(
            records_submitted=records_submitted,
            baseline_consumer_lag=baseline_consumer_lag,
            consumer_lag_growth=consumer_lag_growth,
            consumer_lag_after_recovery=lag_after_recovery,
            baseline_replay_consumer_lag=baseline_replay_consumer_lag,
            replay_consumer_lag_after_recovery=replay_consumer_lag_after_recovery,
            transaction_processing_recovery_seconds=recovery_seconds,
            max_recovery_seconds=args.max_recovery_seconds,
            counts=counts,
            dlq_events_added_during_recovery=dlq_events_added,
            recovery_terminal_reason=recovery_polling.terminal_reason,
        )

        ended_at = datetime.now(UTC)
        result = RecoveryResult(
            run_id=run_id,
            started_at=run_started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            interruption_service=args.interruption_service,
            interruption_container_id=interruption_container_id,
            requested_interruption_seconds=args.interruption_seconds,
            actual_interruption_seconds=actual_interruption_seconds,
            transaction_topic=args.transaction_topic,
            consumer_group=args.consumer_group,
            records_submitted=records_submitted,
            source_persistence_seconds=source_persistence_seconds,
            baseline_consumer_lag=baseline_consumer_lag,
            peak_consumer_lag_during_interruption=peak_consumer_lag,
            consumer_lag_growth=consumer_lag_growth,
            consumer_lag_after_recovery=lag_after_recovery,
            baseline_replay_consumer_lag=baseline_replay_consumer_lag,
            replay_consumer_lag_after_recovery=replay_consumer_lag_after_recovery,
            transaction_processing_recovery_seconds=recovery_seconds,
            transaction_count=counts.transaction_count,
            cost_count=counts.cost_count,
            cashflow_count=counts.cashflow_count,
            position_count=counts.position_count,
            processing_claim_count=counts.processing_claim_count,
            dlq_events_added_during_recovery=dlq_events_added,
            recovery_polling=recovery_polling,
            recovery_mode=recovery_mode.value,
            checks_passed=not failed_checks,
            failed_checks=failed_checks,
        )
        json_path, markdown_path = _write_report(
            output_dir=repo_root / args.output_dir,
            result=result,
        )
        print(f"Wrote failure recovery JSON report: {json_path}")
        print(f"Wrote failure recovery Markdown report: {markdown_path}")
        if args.enforce and not result.checks_passed:
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
