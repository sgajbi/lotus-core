"""Real-PostgreSQL proof for forward reprocessing temporal compatibility."""

from __future__ import annotations

import runpy
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c166b2c3d52d_fix_reprocessing_temporal_contract.py"
)
CONSTRAINT = "ck_reprocessing_jobs_active_payload_valid"
CUTOVER_REASON = "invalid_reprocessing_job_payload: quarantined during contract cutover"


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _constraint_sql(connection) -> str:
    return next(
        constraint["sqltext"]
        for constraint in inspect(connection).get_check_constraints("reprocessing_jobs")
        if constraint["name"] == CONSTRAINT
    )


@contextmanager
def _predecessor_constraint(migration: dict[str, Any], connection) -> Iterator[None]:
    _bind_operations(migration, connection)
    connection.rollback()
    initial_sql = _constraint_sql(connection)
    connection.rollback()
    transaction = connection.begin()
    try:
        migration["downgrade"]()
        assert "[+-][0-9]{2}:?[0-9]{2}" in _constraint_sql(connection)
        yield
    finally:
        transaction.rollback()

    assert _constraint_sql(connection) == initial_sql


def _insert_job(
    connection,
    *,
    payload: str,
    status: str,
    correlation_id: str,
    failure_reason: str | None = None,
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (
                job_type, payload, status, correlation_id, failure_reason, attempt_count
            ) VALUES (
                'RESET_FX_WATERMARKS', CAST(:payload AS json), :status,
                :correlation_id, :failure_reason, 0
            )
            RETURNING id
            """
        ),
        {
            "payload": payload,
            "status": status,
            "correlation_id": correlation_id,
            "failure_reason": failure_reason,
        },
    ).scalar_one()


@pytest.mark.usefixtures("clean_db")
def test_upgrade_recovers_bare_hour_work_and_coalesces_existing_sibling(db_engine) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.connect() as connection:
        with _predecessor_constraint(migration, connection):
            processing_id = _insert_job(
                connection,
                payload=(
                    '{"from_currency":"CAD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-02",'
                    '"content_hash":"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",'
                    '"generated_at":"2025-01-07T08:00:00+00:00"}'
                ),
                status="PENDING",
                correlation_id="corr-processing-cutover",
            )
            connection.execute(
                text(
                    """
                    UPDATE reprocessing_jobs
                    SET status = 'PROCESSING',
                        lease_owner = 'migration-test-worker',
                        lease_token = '0123456789abcdef0123456789abcdef',
                        lease_expires_at = now() + interval '5 minutes'
                    WHERE id = :processing_id
                    """
                ),
                {"processing_id": processing_id},
            )

            blocked_upgrade = connection.begin_nested()
            with pytest.raises(DBAPIError, match="requires a drained PROCESSING queue"):
                migration["upgrade"]()
            blocked_upgrade.rollback()
            assert "[+-][0-9]{2}:?[0-9]{2}" in _constraint_sql(connection)
            connection.execute(
                text(
                    """
                    UPDATE reprocessing_jobs
                    SET status = 'COMPLETE',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL
                    WHERE id = :processing_id
                    """
                ),
                {"processing_id": processing_id},
            )

            jsonb_unrepresentable_source_id = _insert_job(
                connection,
                payload=(
                    '{"from_currency":"CHF","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-02",'
                    '"content_hash":"sha256:9999999999999999999999999999999999999999999999999999999999999999",'
                    '"generated_at":"2025-01-07T08:00:00+00:00","note":"\\u0000"}'
                ),
                status="FAILED",
                correlation_id="corr-jsonb-unrepresentable",
                failure_reason=CUTOVER_REASON,
            )
            recovered_source_id = _insert_job(
                connection,
                payload=(
                    '{"from_currency":"USD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-04",'
                    '"content_hash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
                    '"generated_at":"2025-01-07T08:00:00-07"}'
                ),
                status="FAILED",
                correlation_id="corr-recovered-source",
                failure_reason=CUTOVER_REASON,
            )
            standalone_source_id = _insert_job(
                connection,
                payload=(
                    '{"from_currency":"EUR","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-03",'
                    '"content_hash":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
                    '"generated_at":"2025-01-07T08:00:00+00"}'
                ),
                status="FAILED",
                correlation_id="corr-standalone-source",
                failure_reason=CUTOVER_REASON,
            )
            pending_id = _insert_job(
                connection,
                payload=(
                    '{"from_currency":"USD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-06",'
                    '"content_hash":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
                    '"generated_at":"2025-01-08T00:00:00+00:00"}'
                ),
                status="PENDING",
                correlation_id="corr-newer-sibling",
            )

            migration["upgrade"]()
            constraint_sql = _constraint_sql(connection)
            assert "[+-][0-9]{2}(:?[0-9]{2}" in constraint_sql

            rows = (
                connection.execute(
                    text(
                        """
                    SELECT id, payload, status, failure_reason, correlation_id
                    FROM reprocessing_jobs
                    WHERE id IN (
                        :jsonb_unrepresentable_source_id,
                        :recovered_source_id,
                        :standalone_source_id,
                        :pending_id
                    )
                       OR (
                           job_type = 'RESET_FX_WATERMARKS'
                           AND status = 'PENDING'
                           AND payload->>'from_currency' = 'EUR'
                           AND payload->>'to_currency' = 'SGD'
                       )
                    ORDER BY id
                    """
                    ),
                    {
                        "jsonb_unrepresentable_source_id": jsonb_unrepresentable_source_id,
                        "recovered_source_id": recovered_source_id,
                        "standalone_source_id": standalone_source_id,
                        "pending_id": pending_id,
                    },
                )
                .mappings()
                .all()
            )
            by_id = {row["id"]: row for row in rows}
            assert by_id[jsonb_unrepresentable_source_id]["status"] == "FAILED"
            assert by_id[jsonb_unrepresentable_source_id]["failure_reason"] == CUTOVER_REASON
            assert by_id[recovered_source_id]["status"] == "FAILED"
            assert by_id[standalone_source_id]["status"] == "FAILED"
            assert by_id[pending_id]["status"] == "PENDING"
            assert by_id[pending_id]["payload"]["earliest_impacted_date"] == "2025-01-04"
            assert by_id[pending_id]["payload"]["generated_at"] == "2025-01-08T00:00:00+00:00"
            assert by_id[pending_id]["correlation_id"] == "corr-newer-sibling"

            standalone = next(
                row
                for row in rows
                if row["id"]
                not in {
                    jsonb_unrepresentable_source_id,
                    recovered_source_id,
                    standalone_source_id,
                    pending_id,
                }
            )
            assert standalone["status"] == "PENDING"
            assert standalone["payload"]["earliest_impacted_date"] == "2025-01-03"
            assert standalone["payload"]["generated_at"] == "2025-01-07T08:00:00+00"
            assert standalone["correlation_id"] == "corr-standalone-source"

            accepted_id = _insert_job(
                connection,
                payload=(
                    '{"from_currency":"GBP","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-09",'
                    '"content_hash":"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
                    '"generated_at":"2025-01-09T08:00:00+00"}'
                ),
                status="PENDING",
                correlation_id="corr-bare-hour-active",
            )
            assert accepted_id > 0

            rejected = connection.begin_nested()
            with pytest.raises(IntegrityError):
                _insert_job(
                    connection,
                    payload=(
                        '{"from_currency":"JPY","to_currency":"SGD",'
                        '"earliest_impacted_date":"2025-01-09",'
                        '"content_hash":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",'
                        '"generated_at":"2025-01-09T08:00:00"}'
                    ),
                    status="PENDING",
                    correlation_id="corr-naive-active",
                )
            rejected.rollback()

            blocked_downgrade = connection.begin_nested()
            with pytest.raises(DBAPIError, match="unsupported by the predecessor constraint"):
                migration["downgrade"]()
            blocked_downgrade.rollback()

            connection.execute(
                text(
                    """
                    UPDATE reprocessing_jobs
                    SET status = 'COMPLETE'
                    WHERE status = 'PENDING'
                      AND job_type = 'RESET_FX_WATERMARKS'
                      AND payload->>'generated_at' IN (
                          '2025-01-07T08:00:00+00', '2025-01-09T08:00:00+00'
                      )
                    """
                )
            )
            migration["downgrade"]()
            assert "[+-][0-9]{2}:?[0-9]{2}" in _constraint_sql(connection)
