"""Real-PostgreSQL proof for the quiesced valuation-lease schema cutover."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

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


def _bind_operations(migration: dict[str, Any], connection) -> Operations:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations
    return operations


def _normalize_to_previous_revision(migration: dict[str, Any], connection) -> None:
    columns = {
        column["name"] for column in inspect(connection).get_columns("portfolio_valuation_jobs")
    }
    if {"valuation_lease_owner", "valuation_lease_expires_at"} <= columns:
        migration["downgrade"]()


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


def test_upgrade_requeues_legacy_claims_and_enforces_atomic_lease_cutover(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        _normalize_to_previous_revision(migration, connection)
        _seed_previous_revision_rows(connection)

        migration["upgrade"]()

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
            column["name"] for column in inspect(connection).get_columns("portfolio_valuation_jobs")
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
