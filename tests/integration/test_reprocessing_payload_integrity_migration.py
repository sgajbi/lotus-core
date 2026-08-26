"""Real-PostgreSQL proof for the reprocessing payload contract cutover."""

from __future__ import annotations

import logging
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
def test_upgrade_quarantines_poisoned_work_and_enforces_active_payloads(db_engine, caplog) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.connect() as connection:
        with _previous_revision(migration, connection):
            processing_id = _insert_json_job(
                connection,
                job_type="RESET_WATERMARKS",
                payload=(
                    '{"security_id":"PROCESSING-GUARD","earliest_impacted_date":"2026-08-25"}'
                ),
                correlation_id="payload-migration-processing-guard",
            )
            connection.execute(
                text(
                    """
                    UPDATE reprocessing_jobs
                    SET status = 'PROCESSING',
                        lease_owner = 'payload-migration-proof',
                        lease_token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                        lease_expires_at = clock_timestamp() + INTERVAL '15 minutes'
                    WHERE id = :job_id
                    """
                ),
                {"job_id": processing_id},
            )
            guarded_upgrade = connection.begin_nested()
            with pytest.raises(DBAPIError, match="requires a drained PROCESSING queue"):
                migration["upgrade"]()
            guarded_upgrade.rollback()
            assert not _has_constraint(connection)
            connection.execute(
                text(
                    """
                    UPDATE reprocessing_jobs
                    SET status = 'COMPLETE', lease_owner = NULL,
                        lease_token = NULL, lease_expires_at = NULL
                    WHERE id = :job_id
                    """
                ),
                {"job_id": processing_id},
            )

            nul_id = connection.execute(
                text(
                    r"""
                    INSERT INTO reprocessing_jobs (
                        job_type, payload, status, correlation_id, attempt_count,
                        lease_owner, lease_token, lease_expires_at
                    ) VALUES (
                        'RESET_FX_WATERMARKS',
                        CAST(
                            '{"from_currency":"NU\u0000L","to_currency":"SGD",'
                            '"earliest_impacted_date":"2026-08-25","content_hash":"nul",'
                            '"generated_at":"2026-08-25T00:00:00+00:00"}'
                            AS JSON
                        ),
                        'PROCESSING', 'payload-migration-nul', 1,
                        'payload-migration-worker',
                        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                        clock_timestamp() - INTERVAL '30 minutes'
                    )
                    RETURNING id
                    """
                )
            ).scalar_one()
            unsupported_payload = connection.begin_nested()
            with pytest.raises(DBAPIError, match="active row.*cannot be safely extracted"):
                migration["upgrade"]()
            unsupported_payload.rollback()
            assert not _has_constraint(connection)
            connection.execute(
                text("DELETE FROM reprocessing_jobs WHERE id = :job_id"),
                {"job_id": nul_id},
            )

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
                payload=('{"security_id":"INVALID-DATE","earliest_impacted_date":"2026-99-99"}'),
                correlation_id="payload-migration-invalid-security",
            )
            non_string_identity_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":123,"to_currency":"SGD",'
                    '"earliest_impacted_date":"2026-08-25","content_hash":"scalar",'
                    '"generated_at":"2026-08-25T00:00:00+00:00"}'
                ),
                correlation_id="payload-migration-non-string-identity",
            )
            infinity_date_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"CHF","to_currency":"SGD",'
                    '"earliest_impacted_date":"infinity","content_hash":"infinite",'
                    '"generated_at":"2026-08-25T00:00:00+00:00"}'
                ),
                correlation_id="payload-migration-infinity-date",
            )
            padded_fx_identity_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":" USD ","to_currency":"SGD",'
                    '"earliest_impacted_date":"2026-08-25","content_hash":"padded",'
                    '"generated_at":"2026-08-25T00:00:00+00:00"}'
                ),
                correlation_id="payload-migration-padded-fx-identity",
            )
            control_padded_fx_identity_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"\\tUSD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2026-08-25","content_hash":"control",'
                    '"generated_at":"2026-08-25T00:00:00+00:00"}'
                ),
                correlation_id="payload-migration-control-padded-fx-identity",
            )
            unicode_padded_fx_identity_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"\\u00a0CHF","to_currency":"SGD",'
                    '"earliest_impacted_date":"2026-08-25","content_hash":"unicode",'
                    '"generated_at":"2026-08-25T00:00:00+00:00"}'
                ),
                correlation_id="payload-migration-unicode-padded-fx-identity",
            )
            padded_security_identity_id = _insert_json_job(
                connection,
                job_type="RESET_WATERMARKS",
                payload=('{"security_id":" SEC-1 ","earliest_impacted_date":"2026-08-25"}'),
                correlation_id="payload-migration-padded-security-identity",
            )
            literal_escape_id = _insert_json_job(
                connection,
                job_type="RESET_WATERMARKS",
                payload=(
                    '{"security_id":"SAFE\\\\u0000-TEXT","earliest_impacted_date":"2026-08-25"}'
                ),
                correlation_id="payload-migration-literal-escape",
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
            basic_date_id = _insert_json_job(
                connection,
                job_type="RESET_WATERMARKS",
                payload=('{"security_id":"BASIC-DATE","earliest_impacted_date":"20250825"}'),
                correlation_id="payload-migration-basic-date",
            )
            space_timestamp_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"GBP","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-07","content_hash":"flexible",'
                    '"generated_at":"2025-01-07 08:00:00+05:30"}'
                ),
                correlation_id="payload-migration-space-timestamp",
            )
            minute_timestamp_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"JPY","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-07","content_hash":"minute",'
                    '"generated_at":"2025-01-07T08:00Z"}'
                ),
                correlation_id="payload-migration-minute-timestamp",
            )
            offset_seconds_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"AUD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-07","content_hash":"offset-seconds",'
                    '"generated_at":"2025-01-07T08:00:00+05:30:15"}'
                ),
                correlation_id="payload-migration-offset-seconds",
            )
            basic_timestamp_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"NZD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-07","content_hash":"basic-time",'
                    '"generated_at":"20250107T080000+0530"}'
                ),
                correlation_id="payload-migration-basic-timestamp",
            )
            date_only_timestamp_id = _insert_json_job(
                connection,
                job_type="RESET_FX_WATERMARKS",
                payload=(
                    '{"from_currency":"CAD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-07","content_hash":"date-only",'
                    '"generated_at":"2025-01-07"}'
                ),
                correlation_id="payload-migration-date-only-timestamp",
            )

            connection.execute(text("SET LOCAL client_min_messages = notice"))
            caplog.set_level(logging.INFO, logger="sqlalchemy.dialects.postgresql")
            migration["upgrade"]()
            assert _has_constraint(connection)
            assert any(
                "quarantined 7 FX and 2 security replay row(s)" in record.getMessage()
                for record in caplog.records
            )
            rows = connection.execute(
                text(
                    """
                    SELECT id, status, failure_reason
                    FROM reprocessing_jobs
                    WHERE id IN (
                        :invalid_fx_id, :invalid_security_id, :non_string_identity_id,
                        :infinity_date_id, :padded_fx_identity_id,
                        :control_padded_fx_identity_id, :unicode_padded_fx_identity_id,
                        :padded_security_identity_id,
                        :literal_escape_id, :valid_id, :basic_date_id,
                        :space_timestamp_id, :minute_timestamp_id, :offset_seconds_id,
                        :basic_timestamp_id, :date_only_timestamp_id
                    )
                    ORDER BY id
                    """
                ),
                {
                    "invalid_fx_id": invalid_fx_id,
                    "invalid_security_id": invalid_security_id,
                    "non_string_identity_id": non_string_identity_id,
                    "infinity_date_id": infinity_date_id,
                    "padded_fx_identity_id": padded_fx_identity_id,
                    "control_padded_fx_identity_id": control_padded_fx_identity_id,
                    "unicode_padded_fx_identity_id": unicode_padded_fx_identity_id,
                    "padded_security_identity_id": padded_security_identity_id,
                    "literal_escape_id": literal_escape_id,
                    "valid_id": valid_id,
                    "basic_date_id": basic_date_id,
                    "space_timestamp_id": space_timestamp_id,
                    "minute_timestamp_id": minute_timestamp_id,
                    "offset_seconds_id": offset_seconds_id,
                    "basic_timestamp_id": basic_timestamp_id,
                    "date_only_timestamp_id": date_only_timestamp_id,
                },
            ).all()
            by_id = {row.id: row for row in rows}
            assert by_id[invalid_fx_id].status == "FAILED"
            assert by_id[invalid_security_id].status == "FAILED"
            assert by_id[non_string_identity_id].status == "FAILED"
            assert by_id[infinity_date_id].status == "FAILED"
            assert by_id[padded_fx_identity_id].status == "FAILED"
            assert by_id[control_padded_fx_identity_id].status == "FAILED"
            assert by_id[unicode_padded_fx_identity_id].status == "FAILED"
            assert by_id[padded_security_identity_id].status == "FAILED"
            assert by_id[date_only_timestamp_id].status == "FAILED"
            assert by_id[literal_escape_id].status == "PENDING"
            assert by_id[valid_id].status == "PENDING"
            assert by_id[basic_date_id].status == "PENDING"
            assert by_id[space_timestamp_id].status == "PENDING"
            assert by_id[minute_timestamp_id].status == "PENDING"
            assert by_id[offset_seconds_id].status == "PENDING"
            assert by_id[basic_timestamp_id].status == "PENDING"
            assert all(
                by_id[job_id].failure_reason
                == "invalid_reprocessing_job_payload: quarantined during contract cutover"
                for job_id in (
                    invalid_fx_id,
                    invalid_security_id,
                    non_string_identity_id,
                    infinity_date_id,
                    padded_fx_identity_id,
                    control_padded_fx_identity_id,
                    unicode_padded_fx_identity_id,
                    padded_security_identity_id,
                    date_only_timestamp_id,
                )
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

            non_string_active = connection.begin_nested()
            with pytest.raises(IntegrityError):
                _insert_json_job(
                    connection,
                    job_type="RESET_FX_WATERMARKS",
                    payload=(
                        '{"from_currency":true,"to_currency":"SGD",'
                        '"earliest_impacted_date":"2026-08-25","content_hash":"bad-type",'
                        '"generated_at":"2026-08-25T00:00:00+00:00"}'
                    ),
                    correlation_id="payload-migration-non-string-rejected",
                )
            non_string_active.rollback()

            unicode_padding_active = connection.begin_nested()
            with pytest.raises(IntegrityError):
                _insert_json_job(
                    connection,
                    job_type="RESET_FX_WATERMARKS",
                    payload=(
                        '{"from_currency":"\\u00a0USD","to_currency":"SGD",'
                        '"earliest_impacted_date":"2026-08-25","content_hash":"unicode-active",'
                        '"generated_at":"2026-08-25T00:00:00+00:00"}'
                    ),
                    correlation_id="payload-migration-unicode-padding-rejected",
                )
            unicode_padding_active.rollback()

            date_only_active = connection.begin_nested()
            with pytest.raises(IntegrityError):
                _insert_json_job(
                    connection,
                    job_type="RESET_FX_WATERMARKS",
                    payload=(
                        '{"from_currency":"USD","to_currency":"SGD",'
                        '"earliest_impacted_date":"2026-08-25","content_hash":"date-only-active",'
                        '"generated_at":"2026-08-25"}'
                    ),
                    correlation_id="payload-migration-date-only-rejected",
                )
            date_only_active.rollback()

            missing_active = connection.begin_nested()
            with pytest.raises(IntegrityError):
                _insert_json_job(
                    connection,
                    job_type="RESET_WATERMARKS",
                    payload="{}",
                    correlation_id="payload-migration-missing",
                )
            missing_active.rollback()

            migration["downgrade"]()
            assert not _has_constraint(connection)
            migration["upgrade"]()
            assert _has_constraint(connection)
