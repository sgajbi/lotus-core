"""Real-PostgreSQL proof for the quiesced reprocessing-lease cutover."""

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
    / "c161b2c3d528_feat_add_reprocessing_job_leases.py"
)

LEASE_COLUMNS = {"lease_owner", "lease_token", "lease_expires_at"}
LEASE_INDEX = "ix_reprocessing_jobs_processing_lease_recovery"


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _columns(connection) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns("reprocessing_jobs")}


def _indexes(connection) -> set[str]:
    return {index["name"] for index in inspect(connection).get_indexes("reprocessing_jobs")}


@contextmanager
def _previous_revision(migration: dict[str, Any], connection) -> Iterator[None]:
    """Expose the predecessor schema while restoring the checkout schema afterward."""

    _bind_operations(migration, connection)
    connection.rollback()
    initial_columns = _columns(connection)
    initial_indexes = _indexes(connection)
    connection.rollback()
    transaction = connection.begin()
    try:
        if LEASE_COLUMNS <= _columns(connection):
            migration["downgrade"]()
        assert not LEASE_COLUMNS.intersection(_columns(connection))
        assert LEASE_INDEX not in _indexes(connection)
        yield
    finally:
        transaction.rollback()

    assert _columns(connection) == initial_columns
    assert _indexes(connection) == initial_indexes


def _insert_job(connection, *, status: str, suffix: str) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (
                job_type, payload, status, correlation_id, attempt_count
            ) VALUES (
                'RESET_WATERMARKS',
                jsonb_build_object(
                    'security_id', CAST(:security_id AS text),
                    'earliest_impacted_date', '2026-08-25'
                ),
                :status,
                CAST(:correlation_id AS text),
                2
            )
            RETURNING id
            """
        ),
        {
            "security_id": f"LEASE-MIGRATION-{suffix}",
            "status": status,
            "correlation_id": f"lease-migration-{suffix}",
        },
    ).scalar_one()


@pytest.mark.usefixtures("clean_db")
def test_upgrade_requires_quiescence_and_enforces_atomic_lease_state(db_engine) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.connect() as connection:
        with _previous_revision(migration, connection):
            legacy_processing_id = _insert_job(connection, status="PROCESSING", suffix="guard")

            guarded_upgrade = connection.begin_nested()
            with pytest.raises(DBAPIError, match="requires a drained PROCESSING queue"):
                migration["upgrade"]()
            guarded_upgrade.rollback()
            assert not LEASE_COLUMNS.intersection(_columns(connection))

            connection.execute(
                text("UPDATE reprocessing_jobs SET status = 'PENDING' WHERE id = :job_id"),
                {"job_id": legacy_processing_id},
            )
            complete_id = _insert_job(connection, status="COMPLETE", suffix="complete")

            migration["upgrade"]()
            assert LEASE_COLUMNS <= _columns(connection)
            assert LEASE_INDEX in _indexes(connection)

            rows = connection.execute(
                text(
                    """
                    SELECT id, status, attempt_count, lease_owner, lease_token, lease_expires_at
                    FROM reprocessing_jobs
                    WHERE id IN (:pending_id, :complete_id)
                    ORDER BY id
                    """
                ),
                {"pending_id": legacy_processing_id, "complete_id": complete_id},
            ).all()
            assert all(row.lease_owner is None for row in rows)
            assert all(row.lease_token is None for row in rows)
            assert all(row.lease_expires_at is None for row in rows)
            assert all(row.attempt_count == 2 for row in rows)

            partial_claim = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        UPDATE reprocessing_jobs
                        SET status = 'PROCESSING',
                            lease_token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
                        WHERE id = :job_id
                        """
                    ),
                    {"job_id": legacy_processing_id},
                )
            partial_claim.rollback()

            for lease_owner, lease_token in (
                (" ", "c" * 32),
                (" padded-owner ", "c" * 32),
                ("valid-owner", "C" * 32),
                ("valid-owner", "c" * 31),
                ("valid-owner", "c" * 33),
            ):
                invalid_claim = connection.begin_nested()
                with pytest.raises(DBAPIError):
                    connection.execute(
                        text(
                            """
                            UPDATE reprocessing_jobs
                            SET status = 'PROCESSING',
                                lease_owner = :lease_owner,
                                lease_token = :lease_token,
                                lease_expires_at = clock_timestamp() + INTERVAL '15 minutes'
                            WHERE id = :job_id
                            """
                        ),
                        {
                            "job_id": legacy_processing_id,
                            "lease_owner": lease_owner,
                            "lease_token": lease_token,
                        },
                    )
                invalid_claim.rollback()

            connection.execute(
                text(
                    """
                    UPDATE reprocessing_jobs
                    SET status = 'PROCESSING',
                        lease_owner = 'reprocessing-migration-proof',
                        lease_token = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                        lease_expires_at = clock_timestamp() + INTERVAL '15 minutes'
                    WHERE id = :job_id
                    """
                ),
                {"job_id": legacy_processing_id},
            )
            valid_claim = connection.execute(
                text(
                    """
                    SELECT status, lease_owner, lease_token,
                           lease_expires_at > clock_timestamp() AS lease_active
                    FROM reprocessing_jobs
                    WHERE id = :job_id
                    """
                ),
                {"job_id": legacy_processing_id},
            ).one()
            assert tuple(valid_claim) == (
                "PROCESSING",
                "reprocessing-migration-proof",
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                True,
            )

            guarded_downgrade = connection.begin_nested()
            with pytest.raises(DBAPIError, match="requires a drained PROCESSING queue"):
                migration["downgrade"]()
            guarded_downgrade.rollback()
            assert LEASE_COLUMNS <= _columns(connection)

            connection.execute(
                text(
                    """
                    UPDATE reprocessing_jobs
                    SET status = 'COMPLETE', lease_owner = NULL,
                        lease_token = NULL, lease_expires_at = NULL
                    WHERE id = :job_id
                    """
                ),
                {"job_id": legacy_processing_id},
            )
            migration["downgrade"]()
            assert not LEASE_COLUMNS.intersection(_columns(connection))
            assert LEASE_INDEX not in _indexes(connection)

            migration["upgrade"]()
            reapplied = connection.execute(
                text(
                    """
                    SELECT status, attempt_count, lease_owner, lease_token, lease_expires_at
                    FROM reprocessing_jobs
                    WHERE id = :job_id
                    """
                ),
                {"job_id": legacy_processing_id},
            ).one()
            assert tuple(reapplied) == ("COMPLETE", 2, None, None, None)
