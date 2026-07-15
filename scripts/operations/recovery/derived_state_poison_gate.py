"""Certify poison-message containment and subsequent derived-state progress."""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import requests  # type: ignore[import-untyped]
from portfolio_common.config import (
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
)
from portfolio_common.kafka_utils import KafkaProducer
from sqlalchemy import create_engine

if TYPE_CHECKING:
    from tests.test_support.managed_compose_run import ManagedComposeRun

from scripts.operations.recovery.derived_state_gate import (
    POSITION_TIMESERIES_CONSUMER_GROUP,
    DerivedStateCounts,
    derived_state_counts,
    reconciliation_finding_count,
    seed_market_prices,
    wait_for_full_recovery,
    wait_ready,
)
from scripts.operations.recovery.runtime_support import consumer_lag
from scripts.operations.transaction_processing_cutover_offsets import KafkaOffsetStore
from scripts.operations.transaction_processing_load_support import (
    ingest_transactions,
    seed_load_context,
)
from scripts.quality.ci_service_sets import DERIVED_STATE_RECOVERY_GATE_SERVICES


class RuntimeConnectionEndpoints(Protocol):
    """Expose generated endpoints required by the poison recovery gate."""

    compose_project_name: str
    host_database_url: str
    kafka_bootstrap_servers: str
    e2e_ingestion_url: str
    e2e_event_replay_url: str
    e2e_portfolio_derived_state_url: str
    e2e_financial_reconciliation_url: str


@dataclass(frozen=True, slots=True)
class DerivedStatePoisonResult:
    """Machine-readable evidence for one managed poison-message scenario."""

    run_id: str
    started_at: str
    ended_at: str
    source_topic: str
    consumer_group: str
    dlq_topic: str
    poison_key: str
    poison_correlation_id: str
    poison_evidence_seconds: float | None
    valid_message_recovery_seconds: float | None
    baseline_consumer_lag: int
    final_consumer_lag: int
    baseline_dlq_high_watermark: int
    final_dlq_high_watermark: int
    matching_support_event_count: int
    support_event_ids: tuple[str, ...]
    support_reason_codes: tuple[str, ...]
    counts: DerivedStateCounts
    reconciliation_finding_count: int
    checks_passed: bool
    failed_checks: tuple[str, ...]


def matching_support_events(
    payload: dict[str, Any],
    *,
    original_key: str,
    correlation_id: str,
    source_topic: str,
    consumer_group: str,
) -> tuple[dict[str, Any], ...]:
    """Select exact poison evidence from the operator support projection."""

    events = payload.get("events", [])
    if not isinstance(events, list):
        raise ValueError("consumer DLQ support response events must be a list")
    return tuple(
        cast(dict[str, Any], event)
        for event in events
        if isinstance(event, dict)
        and event.get("original_key") == original_key
        and event.get("correlation_id") == correlation_id
        and event.get("original_topic") == source_topic
        and event.get("consumer_group") == consumer_group
    )


def validate_poison_recovery(
    *,
    expected_position_count: int,
    baseline_consumer_lag: int,
    final_consumer_lag: int,
    baseline_dlq_high_watermark: int,
    final_dlq_high_watermark: int,
    matching_support_event_count: int,
    support_reason_codes: tuple[str, ...],
    recovery_seconds: float | None,
    max_recovery_seconds: int,
    counts: DerivedStateCounts,
    reconciliation_finding_count: int,
) -> tuple[str, ...]:
    """Evaluate exact DLQ, supportability, recovery, and corruption invariants."""

    failures: list[str] = []
    if final_consumer_lag > baseline_consumer_lag:
        failures.append(
            "consumer lag after recovery "
            f"{final_consumer_lag} exceeded baseline {baseline_consumer_lag}"
        )
    dlq_growth = final_dlq_high_watermark - baseline_dlq_high_watermark
    if dlq_growth != 1:
        failures.append(f"DLQ topic grew by {dlq_growth} records instead of exactly 1")
    if matching_support_event_count != 1:
        failures.append(
            "support plane exposed "
            f"{matching_support_event_count} matching poison events instead of exactly 1"
        )
    expected_reason_codes = ("VALIDATION_ERROR",)
    if support_reason_codes != expected_reason_codes:
        failures.append(
            f"support reason codes {support_reason_codes!r} did not equal {expected_reason_codes!r}"
        )
    if recovery_seconds is None:
        failures.append("valid message did not recover before timeout")
    elif recovery_seconds > max_recovery_seconds:
        failures.append(
            f"valid message recovery {recovery_seconds:.3f}s exceeded {max_recovery_seconds}s"
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
    return tuple(failures)


def _topic_high_watermark(*, store: KafkaOffsetStore, topic: str, inspector_group: str) -> int:
    return sum(
        partition.high_watermark
        for partition in store.snapshot(group_id=inspector_group, topic=topic).partitions
    )


def _read_support_events(
    *,
    event_replay_base_url: str,
    ops_token: str,
    source_topic: str,
    consumer_group: str,
) -> dict[str, Any]:
    response = requests.get(
        f"{event_replay_base_url}/ingestion/dlq/consumer-events",
        params={
            "limit": 500,
            "original_topic": source_topic,
            "consumer_group": consumer_group,
        },
        headers={"X-Lotus-Ops-Token": ops_token},
        timeout=20,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _wait_for_support_evidence(
    *,
    event_replay_base_url: str,
    ops_token: str,
    source_topic: str,
    consumer_group: str,
    original_key: str,
    correlation_id: str,
    timeout_seconds: int,
) -> tuple[float | None, tuple[dict[str, Any], ...]]:
    started = time.monotonic()
    deadline = started + timeout_seconds
    matches: tuple[dict[str, Any], ...] = ()
    while time.monotonic() < deadline:
        matches = matching_support_events(
            _read_support_events(
                event_replay_base_url=event_replay_base_url,
                ops_token=ops_token,
                source_topic=source_topic,
                consumer_group=consumer_group,
            ),
            original_key=original_key,
            correlation_id=correlation_id,
            source_topic=source_topic,
            consumer_group=consumer_group,
        )
        if matches:
            return round(time.monotonic() - started, 3), matches
        time.sleep(1)
    return None, matches


def _publish_poison_message(
    *,
    producer: KafkaProducer,
    source_topic: str,
    poison_key: str,
    correlation_id: str,
    portfolio_id: str,
) -> None:
    producer.publish_message(
        topic=source_topic,
        key=poison_key,
        value={
            "event_type": "DailyPositionSnapshotPersisted",
            "schema_version": "1.0",
            "portfolio_id": portfolio_id,
            "correlation_id": correlation_id,
        },
        headers=[("correlation_id", correlation_id.encode("utf-8"))],
    )
    undelivered_count = producer.flush(timeout=10)
    if undelivered_count:
        raise RuntimeError(f"poison publication left {undelivered_count} undelivered messages")


def write_report(*, output_dir: Path, result: DerivedStatePoisonResult) -> tuple[Path, Path]:
    """Write JSON and operator-readable Markdown poison recovery evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{result.run_id}-derived-state-poison-gate.json"
    markdown_path = output_dir / f"{result.run_id}-derived-state-poison-gate.md"
    json_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    markdown_path.write_text(
        "\n".join(
            [
                f"# Derived-State Poison Gate {result.run_id}",
                "",
                f"- Passed: {result.checks_passed}",
                f"- Poison evidence seconds: {result.poison_evidence_seconds}",
                f"- Valid-message recovery seconds: {result.valid_message_recovery_seconds}",
                f"- DLQ topic growth: "
                f"{result.final_dlq_high_watermark - result.baseline_dlq_high_watermark}",
                f"- Matching support events: {result.matching_support_event_count}",
                f"- Final consumer lag: {result.final_consumer_lag}",
                f"- Reconciliation findings: {result.reconciliation_finding_count}",
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
        )
        + "\n",
        encoding="utf-8",
    )
    return json_path, markdown_path


def prepare_managed_run(*, args: argparse.Namespace, repo_root: Path) -> ManagedComposeRun:
    """Prepare one isolated Compose runtime for poison recovery evidence."""

    from tests.test_support.managed_compose_run import prepare_managed_compose_run

    compose_file = Path(args.compose_file)
    if not compose_file.is_absolute():
        compose_file = repo_root / compose_file
    return prepare_managed_compose_run(
        profile="integration",
        scope="derived-state-poison-gate",
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
        / "derived-state-poison-gate-compose.log",
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
    parser.add_argument("--dlq-topic", default=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC)
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--ops-token", default="lotus-core-ops-local")
    parser.add_argument("--ready-timeout-seconds", type=int, default=300)
    parser.add_argument("--poison-timeout-seconds", type=int, default=120)
    parser.add_argument("--recovery-timeout-seconds", type=int, default=300)
    parser.add_argument("--max-recovery-seconds", type=int, default=240)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--keep-stack-up", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    return parser


def main() -> int:
    """Execute one poison event followed by one valid derived-state event."""

    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    started_at = datetime.now(UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    business_date = started_at.date().isoformat()
    portfolio_id = f"DERIVED_POISON_{run_id}"
    security_prefix = f"DP_{run_id[-9:-1]}_SEC"
    poison_key = f"POISON-{run_id}"
    poison_correlation_id = f"DPS:{run_id}"

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
        producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            service_name="derived-state-poison-gate",
        )
        lifecycle.callback(producer.close)

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

        baseline_lag = consumer_lag(
            store=offset_store,
            consumer_group=args.consumer_group,
            topic=args.source_topic,
        )
        inspector_group = f"derived-state-poison-inspector-{run_id}"
        baseline_dlq_high_watermark = _topic_high_watermark(
            store=offset_store,
            topic=args.dlq_topic,
            inspector_group=inspector_group,
        )
        _publish_poison_message(
            producer=producer,
            source_topic=args.source_topic,
            poison_key=poison_key,
            correlation_id=poison_correlation_id,
            portfolio_id=portfolio_id,
        )
        poison_evidence_seconds, _ = _wait_for_support_evidence(
            event_replay_base_url=event_replay_base_url,
            ops_token=args.ops_token,
            source_topic=args.source_topic,
            consumer_group=args.consumer_group,
            original_key=poison_key,
            correlation_id=poison_correlation_id,
            timeout_seconds=args.poison_timeout_seconds,
        )

        valid_started = time.monotonic()
        ingest_transactions(
            ingestion_base_url=ingestion_base_url,
            portfolio_id=portfolio_id,
            batches=1,
            batch_size=1,
            sleep_seconds_between_batches=0,
            seed_prefix=f"DERIVED-VALID-{run_id}",
            security_prefix=security_prefix,
            transaction_date=f"{business_date}T09:00:00Z",
        )
        recovery_seconds, counts, final_lag = wait_for_full_recovery(
            store=offset_store,
            engine=engine,
            consumer_group=args.consumer_group,
            topic=args.source_topic,
            baseline_lag=baseline_lag,
            portfolio_id=portfolio_id,
            business_date=business_date,
            expected_position_count=1,
            timeout_seconds=args.recovery_timeout_seconds,
        )
        if recovery_seconds is not None:
            recovery_seconds = round(time.monotonic() - valid_started, 3)

        support_events = matching_support_events(
            _read_support_events(
                event_replay_base_url=event_replay_base_url,
                ops_token=args.ops_token,
                source_topic=args.source_topic,
                consumer_group=args.consumer_group,
            ),
            original_key=poison_key,
            correlation_id=poison_correlation_id,
            source_topic=args.source_topic,
            consumer_group=args.consumer_group,
        )
        final_dlq_high_watermark = _topic_high_watermark(
            store=offset_store,
            topic=args.dlq_topic,
            inspector_group=inspector_group,
        )
        counts = derived_state_counts(
            engine=engine,
            portfolio_id=portfolio_id,
            business_date=business_date,
        )
        finding_count = reconciliation_finding_count(
            reconciliation_base_url=reconciliation_base_url,
            portfolio_id=portfolio_id,
            business_date=business_date,
        )
        support_reason_codes = tuple(
            sorted(str(event.get("error_reason_code")) for event in support_events)
        )
        failures = validate_poison_recovery(
            expected_position_count=1,
            baseline_consumer_lag=baseline_lag,
            final_consumer_lag=final_lag,
            baseline_dlq_high_watermark=baseline_dlq_high_watermark,
            final_dlq_high_watermark=final_dlq_high_watermark,
            matching_support_event_count=len(support_events),
            support_reason_codes=support_reason_codes,
            recovery_seconds=recovery_seconds,
            max_recovery_seconds=args.max_recovery_seconds,
            counts=counts,
            reconciliation_finding_count=finding_count,
        )
        result = DerivedStatePoisonResult(
            run_id=run_id,
            started_at=started_at.isoformat(),
            ended_at=datetime.now(UTC).isoformat(),
            source_topic=args.source_topic,
            consumer_group=args.consumer_group,
            dlq_topic=args.dlq_topic,
            poison_key=poison_key,
            poison_correlation_id=poison_correlation_id,
            poison_evidence_seconds=poison_evidence_seconds,
            valid_message_recovery_seconds=recovery_seconds,
            baseline_consumer_lag=baseline_lag,
            final_consumer_lag=final_lag,
            baseline_dlq_high_watermark=baseline_dlq_high_watermark,
            final_dlq_high_watermark=final_dlq_high_watermark,
            matching_support_event_count=len(support_events),
            support_event_ids=tuple(str(event.get("event_id")) for event in support_events),
            support_reason_codes=support_reason_codes,
            counts=counts,
            reconciliation_finding_count=finding_count,
            checks_passed=not failures,
            failed_checks=failures,
        )
        json_path, markdown_path = write_report(
            output_dir=repo_root / args.output_dir,
            result=result,
        )
        print(f"Wrote derived-state poison JSON report: {json_path}")
        print(f"Wrote derived-state poison Markdown report: {markdown_path}")
        return 1 if args.enforce and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
