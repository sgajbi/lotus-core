"""Real-PostgreSQL proof for the quiesced valuation-lease schema cutover."""

from __future__ import annotations

import runpy
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c156b2c3d523_feat_add_valuation_claim_leases.py"
)
HOT_PATH_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c160b2c3d527_perf_bound_valuation_job_hot_paths.py"
)

OLD_INDEX = "ix_portfolio_valuation_jobs_processing_lease_expiry"
NEW_INDEX = "ix_portfolio_valuation_jobs_processing_lease_recovery"


def _bind_operations(migration: dict[str, Any], connection) -> Operations:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations
    return operations


def _valuation_job_indexes(connection) -> set[str]:
    return {index["name"] for index in inspect(connection).get_indexes("portfolio_valuation_jobs")}


def _restore_current_hot_path_index(
    hot_path_migration: dict[str, Any],
    connection,
) -> None:
    indexes = _valuation_job_indexes(connection)
    connection.rollback()
    if NEW_INDEX not in indexes:
        hot_path_migration["upgrade"]()


def _normalize_to_previous_revision(migration: dict[str, Any], connection) -> None:
    columns = {
        column["name"] for column in inspect(connection).get_columns("portfolio_valuation_jobs")
    }
    if {"valuation_lease_owner", "valuation_lease_expires_at"} <= columns:
        migration["downgrade"]()


@contextmanager
def _lease_migration_predecessor(
    migration: dict[str, Any],
    hot_path_migration: dict[str, Any],
    connection,
) -> Iterator[None]:
    _bind_operations(migration, connection)
    _bind_operations(hot_path_migration, connection)

    try:
        hot_path_migration["downgrade"]()
        assert OLD_INDEX in _valuation_job_indexes(connection)
        assert NEW_INDEX not in _valuation_job_indexes(connection)
        connection.rollback()

        transaction = connection.begin()
        try:
            _normalize_to_previous_revision(migration, connection)
            assert OLD_INDEX not in _valuation_job_indexes(connection)
            yield
        finally:
            transaction.rollback()

        assert OLD_INDEX in _valuation_job_indexes(connection)
        assert NEW_INDEX not in _valuation_job_indexes(connection)
    finally:
        _restore_current_hot_path_index(hot_path_migration, connection)

    assert NEW_INDEX in _valuation_job_indexes(connection)
    assert OLD_INDEX not in _valuation_job_indexes(connection)


def _seed_previous_revision_rows(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolio_valuation_jobs (
                portfolio_id, security_id, valuation_date, epoch, status,
                requeue_requested, attempt_count, valuation_claim_token
            ) VALUES
                ('P-LEASE-MIGRATION', 'S-PENDING', DATE '2026-08-12', 1,
                 'PENDING', false, 0, NULL),
                ('P-LEASE-MIGRATION', 'S-PROCESSING', DATE '2026-08-12', 1,
                 'PROCESSING', true, 2, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
                ('P-LEASE-MIGRATION', 'S-COMPLETE', DATE '2026-08-12', 1,
                 'COMPLETE', false, 1, NULL),
                ('P-LEASE-MIGRATION', 'S-FAILED', DATE '2026-08-12', 1,
                 'FAILED', false, 3, NULL)
            """
        )
    )


@pytest.mark.usefixtures("clean_db")
def test_upgrade_requeues_legacy_claims_and_enforces_atomic_lease_cutover(db_engine) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    hot_path_migration: dict[str, Any] = runpy.run_path(str(HOT_PATH_MIGRATION))

    with db_engine.connect() as connection:
        with _lease_migration_predecessor(migration, hot_path_migration, connection):
            _seed_previous_revision_rows(connection)

            migration["upgrade"]()
            assert OLD_INDEX in _valuation_job_indexes(connection)

            rows = {
                row.security_id: row
                for row in connection.execute(
                    text(
                        """
                        SELECT security_id, status, requeue_requested, attempt_count,
                               valuation_lease_owner, valuation_claim_token,
                               valuation_lease_expires_at
                        FROM portfolio_valuation_jobs
                        WHERE portfolio_id = 'P-LEASE-MIGRATION'
                        """
                    )
                ).all()
            }
            assert set(rows) == {"S-PENDING", "S-PROCESSING", "S-COMPLETE", "S-FAILED"}
            processing = rows["S-PROCESSING"]
            assert processing.status == "PENDING"
            assert processing.requeue_requested is False
            assert processing.attempt_count == 2
            assert processing.valuation_lease_owner is None
            assert processing.valuation_claim_token is None
            assert processing.valuation_lease_expires_at is None
            assert rows["S-COMPLETE"].status == "COMPLETE"
            assert rows["S-FAILED"].status == "FAILED"

            old_writer = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        UPDATE portfolio_valuation_jobs
                        SET status = 'PROCESSING',
                            valuation_claim_token = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
                        WHERE portfolio_id = 'P-LEASE-MIGRATION'
                          AND security_id = 'S-PENDING'
                        """
                    )
                )
            old_writer.rollback()

            connection.execute(
                text(
                    """
                    UPDATE portfolio_valuation_jobs
                    SET status = 'PROCESSING',
                        valuation_lease_owner = 'valuation-migration-proof',
                        valuation_claim_token = 'cccccccccccccccccccccccccccccccc',
                        valuation_lease_expires_at = clock_timestamp() + INTERVAL '15 minutes'
                    WHERE portfolio_id = 'P-LEASE-MIGRATION'
                      AND security_id = 'S-PENDING'
                    """
                )
            )
            valid_claim = connection.execute(
                text(
                    """
                    SELECT status, valuation_lease_owner, valuation_claim_token,
                           valuation_lease_expires_at > clock_timestamp() AS lease_active
                    FROM portfolio_valuation_jobs
                    WHERE portfolio_id = 'P-LEASE-MIGRATION'
                      AND security_id = 'S-PENDING'
                    """
                )
            ).one()
            assert tuple(valid_claim) == (
                "PROCESSING",
                "valuation-migration-proof",
                "cccccccccccccccccccccccccccccccc",
                True,
            )

            migration["downgrade"]()
            downgraded_columns = {
                column["name"]
                for column in inspect(connection).get_columns("portfolio_valuation_jobs")
            }
            assert "valuation_lease_owner" not in downgraded_columns
            assert "valuation_lease_expires_at" not in downgraded_columns
            assert (
                connection.execute(
                    text(
                        """
                    SELECT valuation_claim_token
                    FROM portfolio_valuation_jobs
                    WHERE portfolio_id = 'P-LEASE-MIGRATION'
                      AND security_id = 'S-PENDING'
                    """
                    )
                ).scalar_one()
                == "cccccccccccccccccccccccccccccccc"
            )

            migration["upgrade"]()
            reapplied = connection.execute(
                text(
                    """
                    SELECT status, valuation_claim_token, valuation_lease_owner,
                           valuation_lease_expires_at
                    FROM portfolio_valuation_jobs
                    WHERE portfolio_id = 'P-LEASE-MIGRATION'
                      AND security_id = 'S-PENDING'
                    """
                )
            ).one()
            assert tuple(reapplied) == ("PENDING", None, None, None)


@pytest.mark.usefixtures("clean_db")
def test_hot_path_index_is_restored_when_lease_migration_proof_fails(db_engine) -> None:
    hot_path_migration: dict[str, Any] = runpy.run_path(str(HOT_PATH_MIGRATION))
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.connect() as connection:
        with pytest.raises(RuntimeError, match="simulated lease migration assertion failure"):
            with _lease_migration_predecessor(migration, hot_path_migration, connection):
                raise RuntimeError("simulated lease migration assertion failure")

        assert NEW_INDEX in _valuation_job_indexes(connection)
        assert OLD_INDEX not in _valuation_job_indexes(connection)
