"""Prove outbox capacity evidence against the repository PostgreSQL runtime."""

from __future__ import annotations

import uuid

from portfolio_common.database_models import OutboxEvent
from sqlalchemy.orm import sessionmaker

from scripts.operations.performance.derived_state_resource_monitor import (
    read_outbox_resource_usage,
)


def test_outbox_resource_totals_tie_to_cohorts_in_one_postgresql_snapshot(
    db_engine,
    clean_db,
) -> None:
    """One sample must not mix status totals with a later cohort snapshot."""

    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    with session_factory.begin() as session:
        session.add_all(
            [
                OutboxEvent(
                    aggregate_type=aggregate_type,
                    aggregate_id=f"resource-snapshot-{uuid.uuid4()}",
                    event_type="ResourceSnapshotTest",
                    topic=topic,
                    payload={},
                    status=status,
                )
                for aggregate_type, topic, status in (
                    ("RawTransaction", "transactions.persisted", "PENDING"),
                    ("RawTransaction", "transactions.persisted", "PROCESSED"),
                    ("DailyPositionSnapshot", "valuation.snapshot.persisted", "FAILED"),
                )
            ]
        )

    usage = read_outbox_resource_usage(engine=db_engine)

    assert usage.pending_events == 1
    assert usage.processed_events == 1
    assert usage.failed_events == 1
    assert sum(count for _, count in usage.pending_events_by_topic) == usage.pending_events
    assert (
        sum(count for _, _, count in usage.pending_events_by_producer_cohort)
        == usage.pending_events
    )
    assert sum(count for _, count in usage.created_events_by_topic) == 3
    assert sum(count for _, _, count in usage.created_events_by_producer_cohort) == 3
