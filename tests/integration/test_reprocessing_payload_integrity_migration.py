"""Real-PostgreSQL proof for the reprocessing payload contract cutover."""

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
    / "c162b2c3d529_fix_harden_reprocessing_payload_integrity.py"
)
CONSTRAINT = "ck_reprocessing_jobs_active_payload_valid"


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _has_constraint(connection) -> bool:
    return CONSTRAINT in {
        constraint["name"]
        for constraint in inspect(connection).get_check_constraints("reprocessing_jobs")
    }


@contextmanager
def _previous_revision(migration: dict[str, Any], connection) -> Iterator[None]:
    """Expose the predecessor schema and restore the checkout schema after proof."""

    _bind_operations(migration, connection)
    connection.rollback()
    constraint_initially_present = _has_constraint(connection)
    connection.rollback()
    transaction = connection.begin()
    try:
        if constraint_initially_present:
            migration["downgrade"]()
        assert not _has_constraint(connection)
        yield
    finally:
        transaction.rollback()

    assert _has_constraint(connection) is constraint_initially_present


def _insert_json_job(
    connection,
    *,
    job_type: str,
    payload: str,
    correlation_id: str,
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (
                job_type, payload, status, correlation_id, attempt_count
            ) VALUES (
                :job_type, CAST(:payload AS json), 'PENDING', :correlation_id, 0
            )
            RETURNING id
            """
        ),
        {
            "job_type": job_type,
            "payload": payload,
            "correlation_id": correlation_id,
        },
    ).scalar_one()


@pytest.mark.usefixtures("clean_db")
def test_upgrade_quarantines_poisoned_work_and_enforces_active_payloads(db_engine) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.connect() as connection:
        with _previous_revision(migration, connection):
            invalid_fx_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"USD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2026-08-25","content_hash":"bad",'
                    '"generated_at":"not-a-timestamp"}'
                ),
                correlation_id="payload-migration-invalid-fx",
            )
            invalid_security_id = _insert_json_job(
                connection,
                job_type="RESET_WATERMARKS",
                payload=(
                    '{"security_id":"INVALID-DATE",'
                    '"earliest_impacted_date":"2026-99-99"}'
                ),
                correlation_id="payload-migration-invalid-security",
            )
            valid_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"EUR","to_currency":"SGD",'
                    '"earliest_impacted_date":"2026-08-25","content_hash":"valid",'
                    '"generated_at":"2026-08-25T00:00:00+00:00"}'
                ),
                correlation_id="payload-migration-valid",
            )

            migration["upgrade"]()
            assert _has_constraint(connection)
            rows = connection.execute(
                text(
                    """
                    SELECT id, status, failure_reason
                    FROM reprocessing_jobs
                    WHERE id IN (:invalid_fx_id, :invalid_security_id, :valid_id)
                    ORDER BY id
                    """
                ),
                {
                    "invalid_fx_id": invalid_fx_id,
                    "invalid_security_id": invalid_security_id,
                    "valid_id": valid_id,
                },
            ).all()
            by_id = {row.id: row for row in rows}
            assert by_id[invalid_fx_id].status == "FAILED"
            assert by_id[invalid_security_id].status == "FAILED"
            assert by_id[valid_id].status == "PENDING"
            assert all(
                by_id[job_id].failure_reason
                == "invalid_reprocessing_job_payload: quarantined during contract cutover"
                for job_id in (invalid_fx_id, invalid_security_id)
            )

            malformed_active = connection.begin_nested()
            with pytest.raises(IntegrityError):
                _insert_json_job(
                    connection,
                    job_type="RESET_FX_WATERMARKS",
                    payload=(
                        '{"from_currency":"GBP","to_currency":"SGD",'
                        '"earliest_impacted_date":"bad","content_hash":"bad",'
                        '"generated_at":"bad"}'
                    ),
                    correlation_id="payload-migration-rejected",
                )
            malformed_active.rollback()

            migration["downgrade"]()
            assert not _has_constraint(connection)
            migration["upgrade"]()
            assert _has_constraint(connection)
