"""Prove outbox capacity evidence against the repository PostgreSQL runtime."""

from __future__ import annotations

import uuid

from portfolio_common.database_models import OutboxEvent
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from scripts.operations.performance.derived_state_resource_monitor import (
    read_database_resource_usage,
    read_outbox_resource_usage,
)


def test_database_resource_usage_attributes_and_reconciles_real_postgresql_sessions(
    db_engine,
    clean_db,
) -> None:
    """Application cohorts must be bounded evidence from the aggregate statement snapshot."""

    with db_engine.connect() as valuation_connection, db_engine.connect() as outbox_connection:
        valuation_connection.execute(
            text("SELECT set_config('application_name', :name, false)"),
            {"name": "portfolio-derived-state"},
        )
        outbox_connection.execute(
            text("SELECT set_config('application_name', :name, false)"),
            {"name": "persistence-service"},
        )

        usage = read_database_resource_usage(engine=db_engine)

    cohorts = {cohort.application_name: cohort for cohort in usage.application_cohorts}
    assert "__unattributed__" in cohorts
    assert cohorts["portfolio-derived-state"].total_connections >= 1
    assert cohorts["portfolio-derived-state"].open_transactions >= 1
    assert cohorts["portfolio-derived-state"].idle_in_transaction_connections >= 1
    assert cohorts["portfolio-derived-state"].oldest_open_transaction_seconds >= 0
    assert cohorts["persistence-service"].total_connections >= 1
    assert sum(cohort.total_connections for cohort in cohorts.values()) == usage.total_connections
    assert sum(cohort.active_connections for cohort in cohorts.values()) == usage.active_connections
    assert (
        sum(cohort.idle_in_transaction_connections for cohort in cohorts.values())
        == usage.idle_in_transaction_connections
    )


def test_database_resource_usage_redacts_ungoverned_application_name(
    db_engine,
    clean_db,
) -> None:
    raw_application_name = "request-PB_SG_GLOBAL_BAL_001"
    with db_engine.connect() as ungoverned_connection:
        ungoverned_connection.execute(
            text("SELECT set_config('application_name', :name, false)"),
            {"name": raw_application_name},
        )

        usage = read_database_resource_usage(engine=db_engine)

    cohorts = {cohort.application_name: cohort for cohort in usage.application_cohorts}
    assert cohorts["__ungoverned__"].total_connections >= 1
    assert raw_application_name not in cohorts


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
