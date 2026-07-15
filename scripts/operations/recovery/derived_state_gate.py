"""Prove bounded interruption recovery of the unified portfolio derived-state runtime."""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol, cast

import requests  # type: ignore[import-untyped]
from portfolio_common.config import KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC
from sqlalchemy import Engine, create_engine, text

if TYPE_CHECKING:
    from tests.test_support.managed_compose_run import ManagedComposeRun

from scripts.operations.recovery.runtime_support import (
    KafkaOffsetReader,
    consumer_lag,
    resolve_interruption_container,
    set_container_pause,
    wait_for_lag_growth,
)
from scripts.operations.transaction_processing_cutover_offsets import KafkaOffsetStore
from scripts.operations.transaction_processing_load_support import (
    ingest_transactions,
    seed_load_context,
    wait_for_database_count,
)
from scripts.quality.ci_service_sets import DERIVED_STATE_RECOVERY_GATE_SERVICES

POSITION_TIMESERIES_CONSUMER_GROUP = "timeseries_generator_group_positions"
DEFAULT_DERIVED_STATE_SERVICE = "portfolio_derived_state_service"


class RuntimeConnectionEndpoints(Protocol):
    """Expose generated endpoints required by the derived-state recovery gate."""

    compose_project_name: str
    host_database_url: str
    kafka_bootstrap_servers: str
    e2e_ingestion_url: str
    e2e_event_replay_url: str
    e2e_portfolio_derived_state_url: str
    e2e_financial_reconciliation_url: str


@dataclass(frozen=True, slots=True)
class DerivedStateCounts:
    """Durable source, output, and open-work counts for one portfolio day."""

    snapshot_count: int
    position_timeseries_count: int
    portfolio_timeseries_count: int
    open_valuation_job_count: int
    open_aggregation_job_count: int


@dataclass(frozen=True, slots=True)
class DerivedStateRecoveryResult:
    """Machine-readable evidence for one controlled runtime interruption."""

    run_id: str
    started_at: str
    ended_at: str
    interruption_service: str
    interruption_container_id: str
    requested_interruption_seconds: int
    actual_interruption_seconds: float
    source_topic: str
    consumer_group: str
    expected_position_count: int
    source_snapshot_materialization_seconds: float
    baseline_consumer_lag: int
    peak_consumer_lag_during_interruption: int
    consumer_lag_growth: int
    consumer_lag_after_recovery: int
    recovery_seconds: float | None
    counts: DerivedStateCounts
    reconciliation_finding_count: int
    dlq_events_added_during_recovery: int
    checks_passed: bool
    failed_checks: tuple[str, ...]


def derived_state_counts(
    *, engine: Engine, portfolio_id: str, business_date: str
) -> DerivedStateCounts:
    """Read exact source, output, and open queue counts for one portfolio day."""

    query = text(
        """
        SELECT
          (
            SELECT count(*) FROM daily_position_snapshots
            WHERE portfolio_id = :portfolio_id AND date = :business_date
          ) AS snapshot_count,
          (
            SELECT count(*) FROM position_timeseries
            WHERE portfolio_id = :portfolio_id AND date = :business_date
          ) AS position_timeseries_count,
          (
            SELECT count(*) FROM portfolio_timeseries
            WHERE portfolio_id = :portfolio_id AND date = :business_date
          ) AS portfolio_timeseries_count,
          (
            SELECT count(*) FROM portfolio_valuation_jobs
            WHERE portfolio_id = :portfolio_id AND valuation_date = :business_date
              AND status IN ('PENDING', 'PROCESSING')
          ) AS open_valuation_job_count,
          (
            SELECT count(*) FROM portfolio_aggregation_jobs
            WHERE portfolio_id = :portfolio_id AND aggregation_date = :business_date
              AND status IN ('PENDING', 'PROCESSING')
          ) AS open_aggregation_job_count
        """
    )
    with engine.connect() as connection:
        row = (
            connection.execute(
                query,
                {"portfolio_id": portfolio_id, "business_date": business_date},
            )
            .mappings()
            .one()
        )
    return DerivedStateCounts(
        snapshot_count=int(row["snapshot_count"]),
        position_timeseries_count=int(row["position_timeseries_count"]),
        portfolio_timeseries_count=int(row["portfolio_timeseries_count"]),
        open_valuation_job_count=int(row["open_valuation_job_count"]),
        open_aggregation_job_count=int(row["open_aggregation_job_count"]),
    )


def wait_for_full_recovery(
    *,
    store: KafkaOffsetReader,
    engine: Engine,
    consumer_group: str,
    topic: str,
    baseline_lag: int,
    portfolio_id: str,
    business_date: str,
    expected_position_count: int,
    timeout_seconds: int,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[float | None, DerivedStateCounts, int]:
    """Wait for exact output completeness, closed queues, and baseline Kafka lag."""

    started = clock()
    deadline = started + timeout_seconds
    counts = DerivedStateCounts(0, 0, 0, 0, 0)
    lag = baseline_lag
    while clock() < deadline:
        counts = derived_state_counts(
            engine=engine,
            portfolio_id=portfolio_id,
            business_date=business_date,
        )
        lag = consumer_lag(store=store, consumer_group=consumer_group, topic=topic)
        if (
            counts.snapshot_count == expected_position_count
            and counts.position_timeseries_count == expected_position_count
            and counts.portfolio_timeseries_count == 1
            and counts.open_valuation_job_count == 0
            and counts.open_aggregation_job_count == 0
            and lag <= baseline_lag
        ):
            return round(clock() - started, 3), counts, lag
        sleeper(1)
    return None, counts, lag


def evaluate_recovery(
    *,
    expected_position_count: int,
    baseline_consumer_lag: int,
    peak_consumer_lag: int,
    consumer_lag_after_recovery: int,
    recovery_seconds: float | None,
    max_recovery_seconds: int,
    counts: DerivedStateCounts,
    reconciliation_finding_count: int,
    dlq_events_added: int,
) -> tuple[str, ...]:
    """Evaluate exact completeness, recovery time, lag, reconciliation, and DLQ invariants."""

    failures: list[str] = []
    lag_growth = max(peak_consumer_lag - baseline_consumer_lag, 0)
    if lag_growth < expected_position_count:
        failures.append(
            f"consumer lag growth {lag_growth} was below expected {expected_position_count}"
        )
    if recovery_seconds is None:
        failures.append("derived-state outputs did not fully recover before timeout")
    elif recovery_seconds > max_recovery_seconds:
        failures.append(
            f"derived-state recovery {recovery_seconds:.3f}s exceeded {max_recovery_seconds}s"
        )
    if consumer_lag_after_recovery > baseline_consumer_lag:
        failures.append(
            "consumer lag after recovery "
            f"{consumer_lag_after_recovery} exceeded baseline {baseline_consumer_lag}"
        )
    expected_counts = {
        "snapshot_count": expected_position_count,
        "position_timeseries_count": expected_position_count,
        "portfolio_timeseries_count": 1,
        "open_valuation_job_count": 0,
        "open_aggregation_job_count": 0,
    }
    for field, expected in expected_counts.items():
        actual = int(getattr(counts, field))
        if actual != expected:
            failures.append(f"{field} {actual} != expected {expected}")
    if reconciliation_finding_count:
        failures.append(f"reconciliation returned {reconciliation_finding_count} findings")
    if dlq_events_added:
        failures.append(f"derived-state recovery added {dlq_events_added} DLQ events")
    return tuple(failures)


def seed_market_prices(
    *,
    engine: Engine,
    ingestion_base_url: str,
    security_prefix: str,
    business_date: str,
    instrument_count: int,
    timeout_seconds: int,
) -> None:
    """Seed deterministic same-currency prices required by position valuation."""

    response = requests.post(
        f"{ingestion_base_url}/ingest/market-prices",
        json={
            "market_prices": [
                {
                    "security_id": f"{security_prefix}_{index:03d}",
                    "price_date": business_date,
                    "price": "101.00",
                    "currency": "USD",
                }
                for index in range(instrument_count)
            ]
        },
        timeout=30,
    )
    if response.status_code != 202:
        raise RuntimeError(
            f"Market-price ingestion failed status={response.status_code}: {response.text[:300]}"
        )
    wait_for_database_count(
        engine=engine,
        sql=(
            "SELECT count(*) FROM market_prices "
            "WHERE security_id LIKE :pattern AND price_date = :business_date"
        ),
        params={"pattern": f"{security_prefix}_%", "business_date": business_date},
        expected=instrument_count,
        label="derived-state recovery market-price seed",
        timeout_seconds=timeout_seconds,
    )


def wait_ready(
    *,
    ingestion_base_url: str,
    event_replay_base_url: str,
    derived_state_base_url: str,
    timeout_seconds: int,
) -> None:
    """Wait until every directly used runtime surface reports ready."""

    deadline = time.time() + timeout_seconds
    urls = (
        f"{ingestion_base_url}/health/ready",
        f"{event_replay_base_url}/health/ready",
        f"{derived_state_base_url}/health/ready",
    )
    while time.time() < deadline:
        try:
            if all(requests.get(url, timeout=5).status_code == 200 for url in urls):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("Derived-state recovery services did not become ready before timeout")


def dlq_event_count(*, event_replay_base_url: str, ops_token: str) -> int:
    """Read the governed recent DLQ count from the ingestion error-budget surface."""

    response = requests.get(
        f"{event_replay_base_url}/ingestion/health/error-budget?lookback_minutes=60",
        headers={"X-Lotus-Ops-Token": ops_token},
        timeout=20,
    )
    response.raise_for_status()
    return int(cast(dict[str, Any], response.json()).get("dlq_events_in_window", 0))


def reconciliation_finding_count(
    *,
    reconciliation_base_url: str,
    portfolio_id: str,
    business_date: str,
) -> int:
    """Run the exact timeseries-integrity reconciliation and return finding count."""

    response = requests.post(
        f"{reconciliation_base_url}/reconciliation/runs/timeseries-integrity",
        json={
            "portfolio_id": portfolio_id,
            "business_date": business_date,
            "epoch": 0,
        },
        timeout=120,
    )
    response.raise_for_status()
    return len(cast(dict[str, Any], response.json()).get("findings", []))


def write_report(*, output_dir: Path, result: DerivedStateRecoveryResult) -> tuple[Path, Path]:
    """Write JSON and operator-readable Markdown recovery evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{result.run_id}-derived-state-recovery-gate.json"
    markdown_path = output_dir / f"{result.run_id}-derived-state-recovery-gate.md"
    json_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    lines = [
        f"# Derived-State Recovery Gate {result.run_id}",
        "",
        f"- Passed: {result.checks_passed}",
        f"- Interrupted service: `{result.interruption_service}`",
        f"- Actual interruption seconds: {result.actual_interruption_seconds}",
        f"- Recovery seconds: {result.recovery_seconds}",
        f"- Consumer lag growth: {result.consumer_lag_growth}",
        f"- Reconciliation findings: {result.reconciliation_finding_count}",
        f"- DLQ events added: {result.dlq_events_added_during_recovery}",
        "",
        "## Durable Counts",
        "",
        "```json",
        json.dumps(asdict(result.counts), indent=2),
        "```",
        "",
        "## Failed Checks",
        "",
        *([f"- {failure}" for failure in result.failed_checks] or ["- none"]),
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def prepare_managed_run(*, args: argparse.Namespace, repo_root: Path) -> ManagedComposeRun:
    """Prepare one isolated Compose runtime for derived-state recovery evidence."""

    from tests.test_support.managed_compose_run import prepare_managed_compose_run

    compose_file = Path(args.compose_file)
    if not compose_file.is_absolute():
        compose_file = repo_root / compose_file
    return prepare_managed_compose_run(
        profile="integration",
        scope="derived-state-recovery-gate",
        compose_project_name=(
            args.compose_project_name
            or (os.getenv("COMPOSE_PROJECT_NAME") if args.skip_compose else None)
        ),
        compose_file=compose_file,
        services=DERIVED_STATE_RECOVERY_GATE_SERVICES,
        build=args.build,
        log_path=repo_root
        / args.output_dir
        / "diagnostics"
        / "derived-state-recovery-gate-compose.log",
        endpoint_urls={
            "E2E_INGESTION_URL": args.ingestion_base_url,
            "E2E_EVENT_REPLAY_URL": args.event_replay_base_url,
            "E2E_PORTFOLIO_DERIVED_STATE_URL": args.derived_state_base_url,
            "E2E_FINANCIAL_RECONCILIATION_URL": args.reconciliation_base_url,
            "HOST_DATABASE_URL": args.host_database_url,
        },
        allocate_dynamic_ports=not args.skip_compose,
        keep_stack=args.keep_stack_up,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the operator CLI without starting external resources."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument("--compose-project-name", default=None)
    parser.add_argument("--ingestion-base-url", default=None)
    parser.add_argument("--event-replay-base-url", default=None)
    parser.add_argument("--derived-state-base-url", default=None)
    parser.add_argument("--reconciliation-base-url", default=None)
    parser.add_argument("--host-database-url", default=None)
    parser.add_argument("--kafka-bootstrap-servers", default=None)
    parser.add_argument("--source-topic", default=KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC)
    parser.add_argument("--consumer-group", default=POSITION_TIMESERIES_CONSUMER_GROUP)
    parser.add_argument("--interruption-service", default=DEFAULT_DERIVED_STATE_SERVICE)
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--ops-token", default="lotus-core-ops-local")
    parser.add_argument("--position-count", type=int, default=10)
    parser.add_argument("--interruption-seconds", type=int, default=15)
    parser.add_argument("--ready-timeout-seconds", type=int, default=300)
    parser.add_argument("--backlog-timeout-seconds", type=int, default=180)
    parser.add_argument("--recovery-timeout-seconds", type=int, default=480)
    parser.add_argument("--max-recovery-seconds", type=int, default=420)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--keep-stack-up", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    return parser


def main() -> int:
    """Execute one controlled interruption and emit deterministic recovery evidence."""

    args = build_parser().parse_args()
    if not 1 <= args.position_count <= 20:
        raise ValueError("position_count must be between 1 and 20")
    repo_root = Path(args.repo_root).resolve()
    started_at = datetime.now(UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    business_date = started_at.date().isoformat()
    portfolio_id = f"DERIVED_RECOVERY_{run_id}"
    security_prefix = f"DR_{run_id[-9:-1]}_SEC"
    transaction_prefix = f"DERIVED-{run_id}"

    from tests.test_support.docker_stack import wait_for_migration_runner

    managed_run = prepare_managed_run(args=args, repo_root=repo_root)
    managed_run.runtime.export_to(os.environ)
    endpoints = cast(RuntimeConnectionEndpoints, managed_run.runtime.endpoints)
    with ExitStack() as lifecycle:
        if not args.skip_compose:
            lifecycle.enter_context(managed_run)
            wait_for_migration_runner(
                managed_run.compose_file,
                timeout_seconds=args.ready_timeout_seconds,
                runtime=managed_run.runtime,
            )
        else:
            managed_run.runtime.port_reservation.release()

        ingestion_base_url = args.ingestion_base_url or endpoints.e2e_ingestion_url
        event_replay_base_url = args.event_replay_base_url or endpoints.e2e_event_replay_url
        derived_state_base_url = (
            args.derived_state_base_url or endpoints.e2e_portfolio_derived_state_url
        )
        reconciliation_base_url = (
            args.reconciliation_base_url or endpoints.e2e_financial_reconciliation_url
        )
        host_database_url = args.host_database_url or endpoints.host_database_url
        kafka_bootstrap_servers = args.kafka_bootstrap_servers or endpoints.kafka_bootstrap_servers
        engine = create_engine(host_database_url, pool_pre_ping=True)
        lifecycle.callback(engine.dispose)
        offset_store = KafkaOffsetStore(
            bootstrap_servers=kafka_bootstrap_servers,
            timeout_seconds=10,
        )
        lifecycle.callback(offset_store.close)

        wait_ready(
            ingestion_base_url=ingestion_base_url,
            event_replay_base_url=event_replay_base_url,
            derived_state_base_url=derived_state_base_url,
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
        seed_market_prices(
            engine=engine,
            ingestion_base_url=ingestion_base_url,
            security_prefix=security_prefix,
            business_date=business_date,
            instrument_count=20,
            timeout_seconds=args.ready_timeout_seconds,
        )

        baseline_dlq = dlq_event_count(
            event_replay_base_url=event_replay_base_url,
            ops_token=args.ops_token,
        )
        baseline_lag = consumer_lag(
            store=offset_store,
            consumer_group=args.consumer_group,
            topic=args.source_topic,
        )
        container_id = resolve_interruption_container(
            repo_root=repo_root,
            compose_file=managed_run.compose_file,
            compose_project_name=endpoints.compose_project_name,
            interruption_service=args.interruption_service,
        )

        interruption_started = time.time()
        set_container_pause(container_id=container_id, paused=True, repo_root=repo_root)
        try:
            ingest_transactions(
                ingestion_base_url=ingestion_base_url,
                portfolio_id=portfolio_id,
                batches=1,
                batch_size=args.position_count,
                sleep_seconds_between_batches=0,
                seed_prefix=transaction_prefix,
                security_prefix=security_prefix,
                transaction_date=f"{business_date}T09:00:00Z",
            )
            source_started = time.time()
            wait_for_database_count(
                engine=engine,
                sql=(
                    "SELECT count(*) FROM daily_position_snapshots "
                    "WHERE portfolio_id = :portfolio_id AND date = :business_date"
                ),
                params={"portfolio_id": portfolio_id, "business_date": business_date},
                expected=args.position_count,
                label="derived-state recovery source snapshots",
                timeout_seconds=args.backlog_timeout_seconds,
            )
            source_seconds = round(time.time() - source_started, 3)
            peak_lag = wait_for_lag_growth(
                store=offset_store,
                consumer_group=args.consumer_group,
                topic=args.source_topic,
                baseline_lag=baseline_lag,
                expected_growth=args.position_count,
                timeout_seconds=args.backlog_timeout_seconds,
            )
            minimum_resume_at = interruption_started + args.interruption_seconds
            if time.time() < minimum_resume_at:
                time.sleep(minimum_resume_at - time.time())
        finally:
            set_container_pause(container_id=container_id, paused=False, repo_root=repo_root)
        interruption_seconds = round(time.time() - interruption_started, 3)

        recovery_seconds, counts, lag_after_recovery = wait_for_full_recovery(
            store=offset_store,
            engine=engine,
            consumer_group=args.consumer_group,
            topic=args.source_topic,
            baseline_lag=baseline_lag,
            portfolio_id=portfolio_id,
            business_date=business_date,
            expected_position_count=args.position_count,
            timeout_seconds=args.recovery_timeout_seconds,
        )
        finding_count = reconciliation_finding_count(
            reconciliation_base_url=reconciliation_base_url,
            portfolio_id=portfolio_id,
            business_date=business_date,
        )
        added_dlq = max(
            dlq_event_count(
                event_replay_base_url=event_replay_base_url,
                ops_token=args.ops_token,
            )
            - baseline_dlq,
            0,
        )
        failures = evaluate_recovery(
            expected_position_count=args.position_count,
            baseline_consumer_lag=baseline_lag,
            peak_consumer_lag=peak_lag,
            consumer_lag_after_recovery=lag_after_recovery,
            recovery_seconds=recovery_seconds,
            max_recovery_seconds=args.max_recovery_seconds,
            counts=counts,
            reconciliation_finding_count=finding_count,
            dlq_events_added=added_dlq,
        )
        result = DerivedStateRecoveryResult(
            run_id=run_id,
            started_at=started_at.isoformat(),
            ended_at=datetime.now(UTC).isoformat(),
            interruption_service=args.interruption_service,
            interruption_container_id=container_id,
            requested_interruption_seconds=args.interruption_seconds,
            actual_interruption_seconds=interruption_seconds,
            source_topic=args.source_topic,
            consumer_group=args.consumer_group,
            expected_position_count=args.position_count,
            source_snapshot_materialization_seconds=source_seconds,
            baseline_consumer_lag=baseline_lag,
            peak_consumer_lag_during_interruption=peak_lag,
            consumer_lag_growth=max(peak_lag - baseline_lag, 0),
            consumer_lag_after_recovery=lag_after_recovery,
            recovery_seconds=recovery_seconds,
            counts=counts,
            reconciliation_finding_count=finding_count,
            dlq_events_added_during_recovery=added_dlq,
            checks_passed=not failures,
            failed_checks=failures,
        )
        json_path, markdown_path = write_report(
            output_dir=repo_root / args.output_dir,
            result=result,
        )
        print(f"Wrote derived-state recovery JSON report: {json_path}")
        print(f"Wrote derived-state recovery Markdown report: {markdown_path}")
        return 1 if args.enforce and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
