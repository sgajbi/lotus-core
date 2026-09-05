import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import portfolio_common.reprocessing_payload_integrity as payload_integrity
import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.infrastructure.persistence.statement_batching import (
    POSTGRES_STATEMENT_ROW_LIMIT,
)
from portfolio_common.reprocessing_job_repository import (
    ReprocessingJobRepository,
    ReprocessingJobTransitionOutcome,
    ResetWatermarksStageOutcome,
)
from portfolio_common.reprocessing_payload_integrity import (
    pending_replay_sibling_evidence,
    quarantine_pending_fx_pair,
)
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.valuation_orchestrator_service.app.core.reprocessing_worker import (
    ReprocessingWorker,
)
from src.services.valuation_orchestrator_service.app.core.reprocessing_worker_dependencies import (
    ReprocessingWorkerRepositoryFactory,
)

pytestmark = pytest.mark.asyncio


async def _wait_for_backend_advisory_lock(
    *, session_factory: async_sessionmaker[AsyncSession], backend_pid: int
) -> None:
    for _ in range(100):
        async with session_factory() as observer:
            wait_event = (
                await observer.execute(
                    text(
                        """
                        SELECT wait_event_type, wait_event
                        FROM pg_stat_activity
                        WHERE pid = :backend_pid
                        """
                    ),
                    {"backend_pid": backend_pid},
                )
            ).one_or_none()
        if wait_event is not None and tuple(wait_event) == ("Lock", "advisory"):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"backend {backend_pid} did not enter an advisory-lock wait")


async def test_stale_security_replay_coalesces_with_newer_pending_job(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    stale_job = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S-STALE", "earliest_impacted_date": "2025-01-05"},
        status="PROCESSING",
        attempt_count=2,
        correlation_id="corr-stale-earliest",
        lease_owner="stale-security-worker",
        lease_token="1" * 32,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    pending_job = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S-STALE", "earliest_impacted_date": "2025-01-07"},
        status="PENDING",
        attempt_count=0,
        correlation_id="corr-pending-later",
    )
    async_db_session.add_all([stale_job, pending_job])
    await async_db_session.commit()

    recovered_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        max_attempts=3
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert recovered_count == 1
    assert len(jobs) == 2
    assert jobs[0].status == "COMPLETE"
    assert jobs[0].failure_reason == (
        "Coalesced into pending security replay during stale recovery"
    )
    assert jobs[1].status == "PENDING"
    assert jobs[1].attempt_count == 2
    assert jobs[1].payload == {
        "security_id": "S-STALE",
        "earliest_impacted_date": "2025-01-05",
    }
    assert jobs[1].correlation_id == "corr-stale-earliest"


async def test_reset_duplicate_normalization_preserves_canonical_identity_and_earliest_date(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": " BOND-CANONICAL",
                    "earliest_impacted_date": "2025-01-05",
                },
                status="PENDING",
                correlation_id="corr-legacy-padded",
                attempt_count=1,
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "BOND-CANONICAL",
                    "earliest_impacted_date": "2025-01-07",
                },
                status="PENDING",
                correlation_id="corr-canonical",
                attempt_count=3,
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "\tBOND-CANONICAL",
                    "earliest_impacted_date": "2025-01-02 BC",
                },
                status="PENDING",
                correlation_id="corr-python-invalid-date",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": " 123", "earliest_impacted_date": "2025-01-04"},
                status="PENDING",
                correlation_id="corr-padded-numeric-text",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": " STRING", "earliest_impacted_date": "2025-01-04"},
                status="PENDING",
                correlation_id="corr-padded-string",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "STRING", "earliest_impacted_date": "2025-01-02 BC"},
                status="PENDING",
                correlation_id="corr-malformed-canonical-string",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "RECOVERY-BOND",
                    "earliest_impacted_date": "not-a-date",
                },
                status="PENDING",
                correlation_id="corr-malformed-recovery-blocker",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "\tTRIM-CONTROL\t",
                    "earliest_impacted_date": "2025-01-02",
                },
                status="PENDING",
                correlation_id="corr-trim-control-source",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": " A\x01A ", "earliest_impacted_date": "2025-01-01"},
                status="PENDING",
                correlation_id="corr-padded-control-string",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "A\x01A", "earliest_impacted_date": "2025-01-02"},
                status="PENDING",
                correlation_id="corr-exact-control-string",
            ),
        ]
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_WATERMARKS', CAST(:payload AS json), 'PENDING', 'corr-numeric-scalar'
            )
            """
        ),
        {
            "payload": (
                '{"security_id":123,"earliest_impacted_date":"2025-01-03",'
                '"unrelated_oversized_number":1e1000000}'
            )
        },
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_WATERMARKS', CAST(:payload AS json), 'PENDING',
                'corr-unbounded-exponent'
            )
            """
        ),
        {
            "payload": (
                '{"security_id":"UNBOUNDED-EXPONENT",'
                '"earliest_impacted_date":"2025-01-03",'
                '"legacy_number":1e9999999999999999999999999999999999999999}'
            )
        },
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_WATERMARKS', CAST(:payload AS json), 'PENDING',
                'corr-numeric-recovery-blocker'
            )
            """
        ),
        {"payload": '{"security_id":456,"earliest_impacted_date":"2025-01-03"}'},
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_WATERMARKS', CAST(:payload AS json), 'PENDING',
                'corr-recoverable-storage-poison'
            )
            """
        ),
        {
            "payload": (
                '{"security_id":" RECOVERY-BOND ",'
                '"earliest_impacted_date":"2025-01-01",'
                '"unrelated_oversized_number":1e1000000}'
            )
        },
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_WATERMARKS', CAST(:payload AS json), 'PENDING',
                'corr-numeric-recovery-source'
            )
            """
        ),
        {
            "payload": (
                '{"security_id":" 456 ","earliest_impacted_date":"2025-01-01",'
                '"unrelated_oversized_number":1e1000000}'
            )
        },
    )
    await async_db_session.commit()

    deleted_count = await ReprocessingJobRepository(
        async_db_session
    ).normalize_pending_reset_watermarks_duplicates()
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (await async_db_session.execute(select(ReprocessingJob))).scalars().all()
    assert deleted_count == 1
    assert len(rows) == 18
    canonical = next(row for row in rows if row.correlation_id == "corr-legacy-padded")
    assert canonical.attempt_count == 3
    malformed = next(row for row in rows if row.correlation_id == "corr-python-invalid-date")
    padded_numeric_text = next(
        row for row in rows if row.correlation_id == "corr-padded-numeric-text"
    )
    numeric_scalar = next(row for row in rows if row.correlation_id == "corr-numeric-scalar")
    unbounded_exponent = next(
        row for row in rows if row.correlation_id == "corr-unbounded-exponent"
    )
    unbounded_boundary = next(
        row
        for row in rows
        if row.status == "PENDING" and row.payload.get("security_id") == "UNBOUNDED-EXPONENT"
    )
    recoverable_source = next(
        row
        for row in rows
        if row.correlation_id == "corr-recoverable-storage-poison" and row.status == "FAILED"
    )
    recovered_boundary = next(
        row
        for row in rows
        if row.status == "PENDING" and row.payload.get("security_id") == "RECOVERY-BOND"
    )
    numeric_recovery_source = next(
        row for row in rows if row.correlation_id == "corr-numeric-recovery-source"
    )
    numeric_recovery_blocker = next(
        row for row in rows if row.correlation_id == "corr-numeric-recovery-blocker"
    )
    numeric_recovered_boundary = next(
        row for row in rows if row.status == "PENDING" and row.payload.get("security_id") == "456"
    )
    padded_string = next(row for row in rows if row.correlation_id == "corr-padded-string")
    malformed_string = next(
        row for row in rows if row.correlation_id == "corr-malformed-canonical-string"
    )
    malformed_recovery_blocker = next(
        row for row in rows if row.correlation_id == "corr-malformed-recovery-blocker"
    )
    trim_control_source = next(
        row for row in rows if row.correlation_id == "corr-trim-control-source"
    )
    trim_control_boundary = next(
        row
        for row in rows
        if row.status == "PENDING" and row.payload.get("security_id") == "TRIM-CONTROL"
    )
    control_rows = [
        row
        for row in rows
        if row.correlation_id in {"corr-padded-control-string", "corr-exact-control-string"}
    ]
    assert canonical.payload == {
        "security_id": "BOND-CANONICAL",
        "earliest_impacted_date": "2025-01-05",
    }
    assert malformed.payload == {
        "security_id": "\tBOND-CANONICAL",
        "earliest_impacted_date": "2025-01-02 BC",
    }
    assert padded_numeric_text.status == "PENDING"
    assert padded_numeric_text.payload == {
        "security_id": "123",
        "earliest_impacted_date": "2025-01-04",
    }
    assert numeric_scalar.status == "FAILED"
    assert numeric_scalar.payload["security_id"] == 123
    assert numeric_scalar.payload["earliest_impacted_date"] == "2025-01-03"
    assert (
        await async_db_session.scalar(
            text(
                "SELECT pg_input_is_valid(payload::text, 'jsonb') "
                "FROM reprocessing_jobs WHERE id = :id"
            ),
            {"id": numeric_scalar.id},
        )
        is False
    )
    assert numeric_scalar.failure_reason == (
        "invalid_reset_watermarks_job_payload: unsafe identity representation"
    )
    assert unbounded_exponent.status == "FAILED"
    assert unbounded_exponent.failure_reason == (
        "invalid_reset_watermarks_job_payload: unsafe retained representation; "
        "replay boundary recovered"
    )
    assert unbounded_boundary.payload == {
        "security_id": "UNBOUNDED-EXPONENT",
        "earliest_impacted_date": "2025-01-03",
    }
    assert recoverable_source.status == "FAILED"
    assert recoverable_source.failure_reason == (
        "invalid_reset_watermarks_job_payload: unsafe retained representation; "
        "replay boundary recovered"
    )
    assert recovered_boundary.payload == {
        "security_id": "RECOVERY-BOND",
        "earliest_impacted_date": "2025-01-01",
    }
    assert numeric_recovery_source.status == "FAILED"
    assert numeric_recovery_source.failure_reason == (
        "invalid_reset_watermarks_job_payload: unsafe retained representation; "
        "replay boundary recovered"
    )
    assert numeric_recovery_blocker.status == "FAILED"
    assert numeric_recovery_blocker.payload == {
        "security_id": 456,
        "earliest_impacted_date": "2025-01-03",
    }
    assert numeric_recovery_blocker.failure_reason == (
        "invalid_reset_watermarks_job_payload: identity collision"
    )
    assert numeric_recovered_boundary.payload == {
        "security_id": "456",
        "earliest_impacted_date": "2025-01-01",
    }
    assert padded_string.status == "PENDING"
    assert padded_string.payload["security_id"] == "STRING"
    assert malformed_string.status == "FAILED"
    assert malformed_string.payload["security_id"] == "STRING"
    assert malformed_string.failure_reason == (
        "invalid_reset_watermarks_job_payload: identity collision"
    )
    assert malformed_recovery_blocker.status == "FAILED"
    assert malformed_recovery_blocker.payload == {
        "security_id": "RECOVERY-BOND",
        "earliest_impacted_date": "not-a-date",
    }
    assert malformed_recovery_blocker.failure_reason == (
        "invalid_reset_watermarks_job_payload: identity collision"
    )
    assert trim_control_source.status == "FAILED"
    assert trim_control_source.failure_reason == (
        "invalid_reset_watermarks_job_payload: unsafe retained representation; "
        "replay boundary recovered"
    )
    assert trim_control_boundary.payload == {
        "security_id": "TRIM-CONTROL",
        "earliest_impacted_date": "2025-01-02",
    }
    assert len(control_rows) == 2
    assert all(row.status == "FAILED" for row in control_rows)
    assert all("\x01" in row.payload["security_id"] for row in control_rows)
    assert all(
        row.failure_reason == "invalid_reset_watermarks_job_payload: unsafe identity representation"
        for row in control_rows
    )


@pytest.mark.parametrize(
    ("encoded_identity", "correlation_id", "expected_escape"),
    [
        ("NUL\\u0000KEY", "corr-nul-identity", "\\u0000"),
        ("BAD\\ud800ID", "corr-surrogate-identity", "\\ud800"),
    ],
)
async def test_reset_normalization_quarantines_unencodable_identity_before_locking(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
    encoded_identity: str,
    correlation_id: str,
    expected_escape: str,
) -> None:
    try:
        with db_engine.begin() as connection:
            connection.execute(
                text('DROP INDEX "uq_reprocessing_jobs_pending_reset_watermarks_security"')
            )
            connection.execute(text('DROP INDEX "ix_reproc_resetwm_sec_status_created_id"'))
            connection.execute(
                text('DROP INDEX "ix_reprocessing_jobs_pending_resetwatermarks_priority"')
            )
            connection.execute(
                text(
                    """
                    INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
                    VALUES
                        (
                            'RESET_WATERMARKS', CAST(:payload AS json), 'PENDING',
                            :correlation_id
                        ),
                        (
                            'RESET_WATERMARKS',
                            CAST(
                                '{"security_id":"VALID",'
                                '"earliest_impacted_date":"2025-01-03"}' AS json
                            ),
                            'PENDING', 'corr-valid-identity'
                        )
                    """
                ),
                {
                    "payload": (
                        f'{{"security_id":"{encoded_identity}",'
                        '"earliest_impacted_date":"2025-01-03"}'
                    ),
                    "correlation_id": correlation_id,
                },
            )
        deleted_count = await ReprocessingJobRepository(
            async_db_session
        ).normalize_pending_reset_watermarks_duplicates()
        await async_db_session.commit()
        evidence = (
            await async_db_session.execute(
                text(
                    """
                    SELECT status, failure_reason, payload::text
                    FROM reprocessing_jobs
                    WHERE correlation_id = :correlation_id
                    """
                ),
                {"correlation_id": correlation_id},
            )
        ).one()
        assert deleted_count == 0
        assert evidence.status == "FAILED"
        assert evidence.failure_reason == (
            "invalid_reset_watermarks_job_payload: unsafe identity representation"
        )
        assert expected_escape in evidence[2]
        valid_status = await async_db_session.scalar(
            text(
                """
                SELECT status
                FROM reprocessing_jobs
                WHERE correlation_id = 'corr-valid-identity'
                """
            )
        )
        assert valid_status == "PENDING"
    finally:
        await async_db_session.rollback()
        with db_engine.begin() as connection:
            connection.execute(text("DELETE FROM reprocessing_jobs"))
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_reprocessing_jobs_pending_reset_watermarks_security
                    ON reprocessing_jobs ((payload->>'security_id'))
                    WHERE job_type = 'RESET_WATERMARKS' AND status = 'PENDING'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                    ix_reprocessing_jobs_pending_resetwatermarks_priority
                    ON reprocessing_jobs (
                        (payload->>'earliest_impacted_date'), created_at, id
                    )
                    WHERE job_type = 'RESET_WATERMARKS' AND status = 'PENDING'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_reproc_resetwm_sec_status_created_id
                    ON reprocessing_jobs (
                        trim(payload->>'security_id'), status, created_at, id
                    )
                    WHERE job_type = 'RESET_WATERMARKS'
                    """
                )
            )


async def test_fx_identity_queries_skip_nul_predecessor_without_blocking_valid_pair(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    try:
        with db_engine.begin() as connection:
            connection.execute(text('DROP INDEX "uq_reproc_jobs_pending_fx_pair"'))
            connection.execute(text('DROP INDEX "ix_reproc_jobs_pending_fx_priority"'))
            connection.execute(
                text(
                    r"""
                    INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
                    VALUES
                        (
                            'RESET_FX_WATERMARKS',
                            CAST(
                                '{"from_currency":"US\u0000D","to_currency":"CAD",'
                                '"earliest_impacted_date":"2025-01-03",'
                                '"generated_at":"2025-01-03T00:00:00+00:00",'
                                '"content_hash":"poisoned"}' AS json
                            ),
                            'PENDING', 'corr-nul-fx-identity'
                        ),
                        (
                            'RESET_FX_WATERMARKS',
                            CAST(
                                '{"from_currency":"USD","to_currency":"SGD",'
                                '"earliest_impacted_date":"2025-01-03",'
                                '"generated_at":"2025-01-03T00:00:00+00:00",'
                                '"content_hash":"valid"}' AS json
                            ),
                            'PENDING', 'corr-valid-fx-identity'
                        )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
                    VALUES (
                      'RESET_FX_WATERMARKS',
                      CAST(:payload AS JSON),
                      'PENDING',
                      'corr-unrelated-fx-poison'
                    )
                    """
                ),
                {
                    "payload": (
                        '{"from_currency":"EUR","to_currency":"GBP",'
                        '"earliest_impacted_date":"2025-01-03",'
                        '"generated_at":"2025-01-03T00:00:00+00:00",'
                        '"content_hash":"unrelated-poison",'
                        '"legacy_number":1e9999999999999999999999999999999999999999}'
                    )
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
                    VALUES (
                      'RESET_FX_WATERMARKS',
                      CAST(:payload AS JSON),
                      'PENDING',
                      'corr-oversized-json-integer'
                    )
                    """
                ),
                {
                    "payload": (
                        '{"from_currency":"JPY","to_currency":"CHF",'
                        '"earliest_impacted_date":"2025-01-04",'
                        '"generated_at":"2025-01-04T00:00:00+00:00",'
                        '"content_hash":"valid-extension",'
                        f'"extension":{("1" * 5_000)}}}'
                    )
                },
            )

        valid_sibling = await pending_replay_sibling_evidence(
            async_db_session,
            job_id=0,
            job_type="RESET_FX_WATERMARKS",
            payload={"from_currency": "USD", "to_currency": "SGD"},
        )
        unrelated_evidence = await quarantine_pending_fx_pair(
            async_db_session,
            from_currency="USD",
            to_currency="SGD",
            validate=lambda payload: payload,
            parse_earliest_date=lambda payload: (
                date.fromisoformat(payload["earliest_impacted_date"])
                if isinstance(payload, dict)
                else None
            ),
        )
        unrelated_status = await async_db_session.scalar(
            select(ReprocessingJob.status).where(
                ReprocessingJob.correlation_id == "corr-unrelated-fx-poison"
            )
        )
        preserved_evidence = await quarantine_pending_fx_pair(
            async_db_session,
            from_currency="EUR",
            to_currency="GBP",
            validate=lambda payload: payload,
            parse_earliest_date=lambda payload: (
                date.fromisoformat(payload["earliest_impacted_date"])
                if isinstance(payload, dict)
                else None
            ),
        )
        oversized_extension_evidence = await quarantine_pending_fx_pair(
            async_db_session,
            from_currency="JPY",
            to_currency="CHF",
            validate=lambda payload: payload,
            parse_earliest_date=lambda payload: (
                date.fromisoformat(payload["earliest_impacted_date"])
                if isinstance(payload, dict)
                else None
            ),
        )
        await async_db_session.commit()
        statuses = dict(
            (
                await async_db_session.execute(
                    select(ReprocessingJob.correlation_id, ReprocessingJob.status)
                )
            ).all()
        )

        assert valid_sibling.exists is True
        assert unrelated_evidence.exists is False
        assert unrelated_status == "PENDING"
        assert preserved_evidence.earliest_sibling.earliest_impacted_date == date(2025, 1, 3)
        assert oversized_extension_evidence.exists is False
        assert statuses["corr-nul-fx-identity"] == "PENDING"
        assert statuses["corr-unrelated-fx-poison"] == "FAILED"
        assert statuses["corr-valid-fx-identity"] == "PENDING"
        assert statuses["corr-oversized-json-integer"] == "PENDING"
    finally:
        await async_db_session.rollback()
        with db_engine.begin() as connection:
            connection.execute(text("DELETE FROM reprocessing_jobs"))
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_reproc_jobs_pending_fx_pair
                    ON reprocessing_jobs (
                        (payload->>'from_currency'), (payload->>'to_currency')
                    )
                    WHERE job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_reproc_jobs_pending_fx_priority
                    ON reprocessing_jobs (
                        (payload->>'earliest_impacted_date'), created_at, id
                    )
                    WHERE job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'
                    """
                )
            )


async def test_reset_normalization_serializes_with_canonical_staging(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    async_db_session.add(
        ReprocessingJob(
            job_type="RESET_WATERMARKS",
            payload={
                "security_id": " RACE-BOND",
                "earliest_impacted_date": "2025-01-03",
            },
            status="PENDING",
            correlation_id="corr-race-padded",
        )
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES ('RESET_WATERMARKS', CAST(:payload AS json), 'PENDING', 'corr-race-poison')
            """
        ),
        {
            "payload": (
                '{"security_id":"UNRELATED-POISON",'
                '"earliest_impacted_date":"2025-01-02","legacy_number":1e1000000}'
            )
        },
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    staging_session = session_factory()
    await staging_session.begin()
    staged = await ReprocessingJobRepository(staging_session).stage_reset_watermarks_job(
        security_id="RACE-BOND",
        earliest_impacted_date=date(2025, 1, 5),
        correlation_id="corr-race-canonical",
    )
    assert staged.outcome == ResetWatermarksStageOutcome.CREATED

    normalizer_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def normalize() -> int:
        async with session_factory() as normalization_session, normalization_session.begin():
            backend_pid = await normalization_session.scalar(select(func.pg_backend_pid()))
            assert backend_pid is not None
            normalizer_pid.set_result(int(backend_pid))
            return await ReprocessingJobRepository(
                normalization_session
            ).normalize_pending_reset_watermarks_duplicates()

    normalization_task = asyncio.create_task(normalize())
    try:
        backend_pid = await asyncio.wait_for(normalizer_pid, timeout=5)
        await _wait_for_backend_advisory_lock(
            session_factory=session_factory,
            backend_pid=backend_pid,
        )
        await staging_session.commit()
        deleted_count = await asyncio.wait_for(normalization_task, timeout=5)
    finally:
        if staging_session.in_transaction():
            await staging_session.rollback()
        await staging_session.close()
        if not normalization_task.done():
            normalization_task.cancel()
            await asyncio.gather(normalization_task, return_exceptions=True)

    async with session_factory() as evidence_session:
        jobs = (
            (
                await evidence_session.execute(
                    select(ReprocessingJob).where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                )
            )
            .scalars()
            .all()
        )
    assert deleted_count == 0
    assert len(jobs) == 4
    canonical = next(job for job in jobs if job.correlation_id == "corr-race-canonical")
    padded = next(job for job in jobs if job.correlation_id == "corr-race-padded")
    poisoned = next(job for job in jobs if job.correlation_id == "corr-race-poison")
    recovered_poisoned_boundary = next(
        job
        for job in jobs
        if job.status == "PENDING" and job.payload.get("security_id") == "UNRELATED-POISON"
    )
    assert canonical.status == "PENDING"
    assert canonical.payload == {
        "security_id": "RACE-BOND",
        "earliest_impacted_date": "2025-01-03",
    }
    assert padded.status == "FAILED"
    assert padded.payload == {
        "security_id": " RACE-BOND",
        "earliest_impacted_date": "2025-01-03",
    }
    assert padded.failure_reason == (
        "invalid_reset_watermarks_job_payload: superseded during valid replay staging"
    )
    assert poisoned.status == "FAILED"
    assert poisoned.failure_reason == (
        "invalid_reset_watermarks_job_payload: unsafe retained representation; "
        "replay boundary recovered"
    )
    assert recovered_poisoned_boundary.payload == {
        "security_id": "UNRELATED-POISON",
        "earliest_impacted_date": "2025-01-02",
    }


async def test_reset_staging_preserves_boundary_claimed_between_scan_and_lock(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    source_id = await async_db_session.scalar(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_WATERMARKS',
                CAST(:payload AS json),
                'PENDING',
                'corr-claim-race-source'
            )
            RETURNING id
            """
        ),
        {
            "payload": (
                '{"security_id":"CLAIM-RACE-BOND",'
                '"earliest_impacted_date":"2025-01-02",'
                '"legacy_number":1e1000000}'
            )
        },
    )
    assert source_id is not None
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    scan_completed = asyncio.Event()
    allow_row_lock = asyncio.Event()
    original_lock = payload_integrity._lock_scanned_replay_rows

    async def pause_after_scan(
        db: AsyncSession,
        *,
        candidate_ids: list[int],
        preserve_candidate_ids: list[int],
        job_type: str,
    ):
        scan_completed.set()
        await allow_row_lock.wait()
        return await original_lock(
            db,
            candidate_ids=candidate_ids,
            preserve_candidate_ids=preserve_candidate_ids,
            job_type=job_type,
        )

    async def stage_boundary():
        async with session_factory() as staging_session, staging_session.begin():
            return await ReprocessingJobRepository(staging_session).stage_reset_watermarks_job(
                security_id="CLAIM-RACE-BOND",
                earliest_impacted_date=date(2025, 1, 9),
                correlation_id="corr-claim-race-staging",
            )

    with patch.object(payload_integrity, "_lock_scanned_replay_rows", side_effect=pause_after_scan):
        staging_task = asyncio.create_task(stage_boundary())
        try:
            await asyncio.wait_for(scan_completed.wait(), timeout=5)
            async with session_factory() as claimant_session, claimant_session.begin():
                claimed = await ReprocessingJobRepository(claimant_session).find_and_claim_jobs(
                    "RESET_WATERMARKS",
                    batch_size=1,
                    lease_owner="claim-race-worker",
                    normalize_reset_watermark_duplicates=False,
                )
                assert [job.id for job in claimed] == [source_id]
            allow_row_lock.set()
            staged = await asyncio.wait_for(staging_task, timeout=5)
        finally:
            allow_row_lock.set()
            if not staging_task.done():
                staging_task.cancel()
                await asyncio.gather(staging_task, return_exceptions=True)

    assert staged.outcome == ResetWatermarksStageOutcome.CREATED
    async with session_factory() as evidence_session:
        rows = (
            (
                await evidence_session.execute(
                    select(ReprocessingJob).where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                )
            )
            .scalars()
            .all()
        )
    source = next(row for row in rows if row.id == source_id)
    replacement = next(row for row in rows if row.id != source_id)
    assert source.status == "PROCESSING"
    assert source.lease_owner == "claim-race-worker"
    assert source.lease_token is not None
    assert replacement.status == "PENDING"
    assert replacement.payload == {
        "security_id": "CLAIM-RACE-BOND",
        "earliest_impacted_date": "2025-01-02",
    }


async def test_unnormalized_predecessor_security_replay_fails_without_rewriting_identity(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    malformed = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={"security_id": " SEC-1 ", "earliest_impacted_date": "2025-01-05"},
        status="PROCESSING",
        attempt_count=1,
        lease_owner="padded-security-worker",
        lease_token="5" * 32,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    async_db_session.add(malformed)
    await async_db_session.commit()
    malformed_id = malformed.id

    repository = ReprocessingJobRepository(async_db_session)
    recovered_count = await repository.find_and_reset_stale_jobs(max_attempts=3)
    valid = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "SEC-1", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-normalized-security",
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    failed = await async_db_session.get(ReprocessingJob, malformed_id)
    assert recovered_count == 0
    assert failed is not None
    assert failed.status == "FAILED"
    assert failed.payload["security_id"] == " SEC-1 "
    assert failed.failure_reason == "Malformed effective-dated replay during stale recovery"
    assert valid.status == "PENDING"
    assert valid.payload["security_id"] == "SEC-1"


async def test_stale_fx_timestamps_are_typed_before_cohort_recovery(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    poisoned_fx = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2025-01-05",
            "content_hash": "sha256:" + ("a" * 64),
            "generated_at": "not-a-timestamp",
        },
        status="PROCESSING",
        attempt_count=1,
        lease_owner="poisoned-fx-worker",
        lease_token="a" * 32,
        lease_expires_at=stale_time,
    )
    separator_poisoned_fx = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2025-01-06",
            "content_hash": "sha256:" + ("c" * 64),
            "generated_at": "2026-08-26Q10:00:00+00:00",
        },
        status="PROCESSING",
        attempt_count=1,
        lease_owner="separator-poisoned-fx-worker",
        lease_token="c" * 32,
        lease_expires_at=stale_time,
    )
    pending_sibling = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2025-01-07",
            "content_hash": "sha256:" + ("b" * 64),
            "generated_at": "2027-01-07T08:00:00+00:00",
        },
        status="PENDING",
        correlation_id="corr-valid-pending-fx",
    )
    recoverable = ReprocessingJob(
        job_type="LEASE_LIFECYCLE_PROOF",
        payload={"scope": "same-stale-cohort"},
        status="PROCESSING",
        attempt_count=1,
        lease_owner="recoverable-worker",
        lease_token="b" * 32,
        lease_expires_at=stale_time,
    )
    async_db_session.add_all([poisoned_fx, separator_poisoned_fx, pending_sibling, recoverable])
    await async_db_session.flush()
    poisoned_id = poisoned_fx.id
    separator_poisoned_id = separator_poisoned_fx.id
    sibling_id = pending_sibling.id
    recoverable_id = recoverable.id
    sibling_payload = dict(pending_sibling.payload)
    await async_db_session.commit()

    recovered_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        max_attempts=3
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    poisoned = await async_db_session.get(ReprocessingJob, poisoned_id)
    separator_poisoned = await async_db_session.get(ReprocessingJob, separator_poisoned_id)
    sibling = await async_db_session.get(ReprocessingJob, sibling_id)
    recovered = await async_db_session.get(ReprocessingJob, recoverable_id)
    assert recovered_count == 2
    assert poisoned is not None
    assert poisoned.status == "FAILED"
    assert poisoned.failure_reason == "Malformed effective-dated replay during stale recovery"
    assert separator_poisoned is not None
    assert separator_poisoned.status == "COMPLETE"
    assert separator_poisoned.failure_reason == (
        "Coalesced into pending FX replay during stale recovery"
    )
    assert sibling is not None
    assert sibling.status == "PENDING"
    assert sibling.payload == {
        **sibling_payload,
        "earliest_impacted_date": "2025-01-06",
    }
    assert sibling.correlation_id == "corr-valid-pending-fx"
    assert recovered is not None
    assert recovered.status == "PENDING"


async def test_timezone_less_stale_fx_fails_without_blocking_valid_work(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    timezone_less_fx = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "CHF",
            "earliest_impacted_date": "2025-01-06",
            "content_hash": "sha256:" + ("d" * 64),
            "generated_at": "2026-08-26T10:00:00",
        },
        status="PROCESSING",
        attempt_count=1,
        lease_owner="timezone-less-fx-worker",
        lease_token="e" * 32,
        lease_expires_at=stale_time,
    )
    recoverable = ReprocessingJob(
        job_type="LEASE_LIFECYCLE_PROOF",
        payload={"scope": "after-timezone-less-fx-replay"},
        status="PROCESSING",
        attempt_count=1,
        lease_owner="recoverable-worker",
        lease_token="f" * 32,
        lease_expires_at=stale_time,
    )
    async_db_session.add_all([timezone_less_fx, recoverable])
    await async_db_session.flush()
    timezone_less_fx_id = timezone_less_fx.id
    recoverable_id = recoverable.id
    await async_db_session.commit()

    recovered_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        max_attempts=3
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    malformed = await async_db_session.get(ReprocessingJob, timezone_less_fx_id)
    recovered = await async_db_session.get(ReprocessingJob, recoverable_id)
    assert recovered_count == 1
    assert malformed is not None
    assert malformed.status == "FAILED"
    assert malformed.failure_reason == "Malformed effective-dated replay during stale recovery"
    assert recovered is not None
    assert recovered.status == "PENDING"


async def test_staging_quarantines_timezone_less_pending_fx_lineage(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    legacy = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "JPY",
            "earliest_impacted_date": "2025-01-04",
            "content_hash": "sha256:" + ("f" * 64),
            "generated_at": "2030-01-01T00:00:00",
        },
        status="PENDING",
        correlation_id="corr-legacy-timezone-less",
    )
    async_db_session.add(legacy)
    await async_db_session.flush()
    legacy_id = legacy.id
    await async_db_session.commit()

    await async_db_session.execute(text("SET LOCAL TIME ZONE 'Asia/Singapore'"))
    await ReprocessingJobRepository(async_db_session).stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="JPY",
        earliest_impacted_date=date(2025, 1, 6),
        content_hash="sha256:" + ("a" * 64),
        generated_at=datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
        correlation_id="corr-authoritative",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert rows[0].id == legacy_id
    assert rows[0].status == "FAILED"
    assert rows[0].failure_reason == (
        "invalid_fx_revaluation_job_payload: superseded during valid replay staging"
    )
    assert rows[1].status == "PENDING"
    assert rows[1].payload["earliest_impacted_date"] == "2025-01-04"
    assert rows[1].payload["generated_at"] == "2026-08-26T10:00:00+00:00"
    assert rows[1].payload["content_hash"] == "sha256:" + ("a" * 64)
    assert rows[1].correlation_id == "corr-authoritative"


async def test_staging_quarantines_postgres_unrepresentable_pending_fx_date(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    legacy = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "EUR",
            "earliest_impacted_date": "2025-W01-2",
            "content_hash": "sha256:" + ("f" * 64),
            "generated_at": "2026-08-26T10:00:00+00:00",
        },
        status="PENDING",
        correlation_id="corr-legacy-week-date",
    )
    async_db_session.add(legacy)
    await async_db_session.flush()
    legacy_id = legacy.id
    await async_db_session.commit()

    await ReprocessingJobRepository(async_db_session).stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="EUR",
        earliest_impacted_date=date(2025, 1, 6),
        content_hash="sha256:" + ("a" * 64),
        generated_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        correlation_id="corr-authoritative",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert rows[0].id == legacy_id
    assert rows[0].status == "FAILED"
    assert rows[1].status == "PENDING"
    assert rows[1].payload["earliest_impacted_date"] == "2024-12-31"
    assert rows[1].payload["generated_at"] == "2026-08-27T10:00:00+00:00"


async def test_staging_retains_newer_fx_authority_around_unbounded_extension(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    retained_hash = "sha256:" + ("f" * 64)
    incoming_hash = "sha256:" + ("a" * 64)
    retained_id = await async_db_session.scalar(
        text(
            """
            INSERT INTO reprocessing_jobs (
                job_type, payload, status, attempt_count, correlation_id
            )
            VALUES (
                'RESET_FX_WATERMARKS', CAST(:payload AS JSON), 'PENDING', 5, 'corr-retained-fx'
            )
            RETURNING id
            """
        ),
        {
            "payload": (
                '{"from_currency":"USD","to_currency":"CAD",'
                '"earliest_impacted_date":"2025-01-03",'
                '"generated_at":"2025-01-08T00:00:00+00:00",'
                f'"content_hash":"{retained_hash}",'
                '"extension":1e999999999999999999999999999999999999999}'
            )
        },
    )
    assert retained_id is not None
    await async_db_session.commit()

    await ReprocessingJobRepository(async_db_session).stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="CAD",
        earliest_impacted_date=date(2025, 1, 6),
        content_hash=incoming_hash,
        generated_at=datetime(2025, 1, 7, tzinfo=timezone.utc),
        correlation_id="corr-incoming-fx",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
        attempt_count=1,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [row.status for row in rows] == ["FAILED", "PENDING"]
    assert rows[0].id == retained_id
    assert rows[1].payload == {
        "from_currency": "USD",
        "to_currency": "CAD",
        "earliest_impacted_date": "2025-01-03",
        "generated_at": "2025-01-08T00:00:00+00:00",
        "content_hash": retained_hash,
    }
    assert rows[1].attempt_count == 5
    assert rows[1].correlation_id == "corr-retained-fx"


async def test_staging_quarantines_postgres_unrepresentable_pending_reset_date(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    legacy = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={
            "security_id": "BOND-WEEK-DATE",
            "earliest_impacted_date": "2025-W01-2",
        },
        status="PENDING",
        attempt_count=5,
        correlation_id="corr-legacy-week-date",
    )
    async_db_session.add(legacy)
    await async_db_session.flush()
    legacy_id = legacy.id
    await async_db_session.commit()

    result = await ReprocessingJobRepository(async_db_session).stage_reset_watermarks_job(
        security_id="BOND-WEEK-DATE",
        earliest_impacted_date=date(2025, 1, 6),
        correlation_id="corr-authoritative",
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert result.outcome is ResetWatermarksStageOutcome.CREATED
    assert len(rows) == 2
    assert rows[0].id == legacy_id
    assert rows[0].status == "FAILED"
    assert rows[0].failure_reason == (
        "invalid_reset_watermarks_job_payload: superseded during valid replay staging"
    )
    assert rows[1].status == "PENDING"
    assert rows[1].payload == {
        "security_id": "BOND-WEEK-DATE",
        "earliest_impacted_date": "2024-12-31",
    }
    assert rows[1].attempt_count == 5
    assert rows[1].correlation_id == "corr-legacy-week-date"


async def test_staging_preserves_valid_compact_offset_pending_fx_lineage(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    compact_offset = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "HKD",
            "earliest_impacted_date": "2025-01-04",
            "content_hash": "sha256:" + ("b" * 64),
            "generated_at": "2025-01-07T08:00:00+0800",
        },
        status="PENDING",
        correlation_id="corr-compact-offset",
    )
    async_db_session.add(compact_offset)
    await async_db_session.flush()
    compact_offset_id = compact_offset.id
    await async_db_session.commit()

    await ReprocessingJobRepository(async_db_session).stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="HKD",
        earliest_impacted_date=date(2025, 1, 6),
        content_hash="sha256:" + ("c" * 64),
        generated_at=datetime(2025, 1, 8, tzinfo=timezone.utc),
        correlation_id="corr-latest-authoritative",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].id == compact_offset_id
    assert rows[0].status == "PENDING"
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-04"
    assert rows[0].payload["generated_at"] == "2025-01-08T00:00:00+00:00"
    assert rows[0].payload["content_hash"] == "sha256:" + ("c" * 64)
    assert rows[0].correlation_id == "corr-latest-authoritative"


async def test_stale_control_character_payload_fails_before_identity_lock_binding(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    inserted = await async_db_session.execute(
        text(
            r"""
            INSERT INTO reprocessing_jobs (
                job_type,
                payload,
                status,
                attempt_count,
                lease_owner,
                lease_token,
                lease_expires_at
            )
            VALUES (
                'RESET_FX_WATERMARKS',
                CAST(
                    '{"from_currency":"US\u0000D","to_currency":"CAD",'
                    '"earliest_impacted_date":"2025-01-04",'
                    '"content_hash":"poisoned-content-hash",'
                    '"generated_at":"2025-01-07T08:00:00+00:00"}'
                    AS JSON
                ),
                'PROCESSING',
                1,
                'control-character-worker',
                '33333333333333333333333333333333',
                clock_timestamp() - interval '30 minutes'
            )
            RETURNING id
            """
        )
    )
    poisoned_id = int(inserted.scalar_one())
    recoverable = ReprocessingJob(
        job_type="LEASE_LIFECYCLE_PROOF",
        payload={"scope": "after-control-character-replay"},
        status="PROCESSING",
        attempt_count=1,
        lease_owner="recoverable-worker",
        lease_token="4" * 32,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    async_db_session.add(recoverable)
    await async_db_session.flush()
    recoverable_id = recoverable.id
    await async_db_session.commit()

    recovered_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        max_attempts=3
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    poisoned = await async_db_session.get(ReprocessingJob, poisoned_id)
    recovered = await async_db_session.get(ReprocessingJob, recoverable_id)
    assert recovered_count == 1
    assert poisoned is not None
    assert poisoned.status == "FAILED"
    assert poisoned.failure_reason == "Malformed effective-dated replay during stale recovery"
    assert recovered is not None
    assert recovered.status == "PENDING"


async def test_find_and_claim_jobs_prioritizes_oldest_pending_reset_watermarks(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN multiple pending RESET_WATERMARKS jobs for different securities
    WHEN the worker-facing claim path runs
    THEN jobs should be claimed by the oldest impacted date first.
    """
    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S1", "earliest_impacted_date": "2025-01-07"},
                status="PENDING",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
                status="PENDING",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S3", "earliest_impacted_date": "2025-01-06"},
                status="PENDING",
            ),
        ]
    )
    await async_db_session.commit()

    repository = ReprocessingJobRepository(async_db_session)

    claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=10)
    await async_db_session.commit()

    assert len(claimed) == 3
    assert claimed[0].payload["security_id"] == "S2"
    assert claimed[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert claimed[1].payload["security_id"] == "S3"
    assert claimed[2].payload["security_id"] == "S1"

    remaining_rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(remaining_rows) == 3
    assert {row.payload["security_id"] for row in remaining_rows} == {"S1", "S2", "S3"}


async def test_find_and_claim_jobs_batch_size_one_updates_exactly_one_row(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S-FIRST", "earliest_impacted_date": "2025-01-05"},
                status="PENDING",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "S-SECOND", "earliest_impacted_date": "2025-01-06"},
                status="PENDING",
            ),
        ]
    )
    await async_db_session.commit()

    claimed = await ReprocessingJobRepository(async_db_session).find_and_claim_jobs(
        "RESET_WATERMARKS",
        batch_size=1,
    )
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(claimed) == 1
    assert claimed[0].payload["security_id"] == "S-FIRST"
    assert [row.status for row in rows] == ["PROCESSING", "PENDING"]
    assert [row.attempt_count for row in rows] == [1, 0]


async def test_find_and_claim_jobs_keeps_malformed_payload_from_blocking_valid_sibling(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES
              ('RESET_WATERMARKS', CAST('null' AS JSON), 'PENDING'),
              (
                'RESET_WATERMARKS',
                CAST('{"security_id":"S-VALID","earliest_impacted_date":"2025-01-05"}' AS JSON),
                'PENDING'
              )
            """
        )
    )
    await async_db_session.commit()

    claimed = await ReprocessingJobRepository(async_db_session).find_and_claim_jobs(
        "RESET_WATERMARKS",
        batch_size=2,
    )
    await async_db_session.commit()

    assert len(claimed) == 2
    assert any(job.payload is None for job in claimed)
    assert any(
        isinstance(job.payload, dict) and job.payload.get("security_id") == "S-VALID"
        for job in claimed
    )


async def test_find_and_claim_jobs_decodes_oversized_extension_without_blocking_batch(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    oversized_integer = "7" * 5_000
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES
              ('RESET_WATERMARKS', CAST(:oversized_payload AS JSON), 'PENDING'),
              ('RESET_WATERMARKS', CAST(:ordinary_payload AS JSON), 'PENDING')
            """
        ),
        {
            "oversized_payload": (
                '{"security_id":"S-LARGE","earliest_impacted_date":"2025-01-05",'
                f'"extension":{oversized_integer}}}'
            ),
            "ordinary_payload": (
                '{"security_id":"S-ORDINARY","earliest_impacted_date":"2025-01-06"}'
            ),
        },
    )
    await async_db_session.commit()

    claimed = await ReprocessingJobRepository(async_db_session).find_and_claim_jobs(
        "RESET_WATERMARKS",
        batch_size=2,
    )
    await async_db_session.commit()

    assert [job.payload["security_id"] for job in claimed] == ["S-LARGE", "S-ORDINARY"]
    assert str(claimed[0].payload["extension"]) == oversized_integer

    repository = ReprocessingJobRepository(async_db_session)
    assert (
        await repository.requeue_owned_effective_dated_job(
            claimed[0].id,
            lease_token=claimed[0].lease_token,
        )
        is ReprocessingJobTransitionOutcome.REQUEUED
    )
    await async_db_session.commit()

    reclaimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    await async_db_session.execute(
        update(ReprocessingJob)
        .where(ReprocessingJob.id == reclaimed.id)
        .values(lease_expires_at=func.clock_timestamp() - text("INTERVAL '1 second'"))
    )
    await async_db_session.commit()

    assert await repository.find_and_reset_stale_jobs(max_attempts=5) == 1
    await async_db_session.commit()
    replay_rows = (
        (
            await async_db_session.execute(
                text(
                    """
                SELECT status, payload::text AS payload_json
                FROM reprocessing_jobs
                WHERE payload->>'security_id' = 'S-LARGE'
                ORDER BY id
                """
                )
            )
        )
        .mappings()
        .all()
    )
    assert [row["status"] for row in replay_rows] == ["COMPLETE", "PENDING"]
    assert "extension" not in replay_rows[1]["payload_json"]


async def test_find_and_claim_fx_job_recovers_canonical_payload_around_unbounded_extension(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    content_hash = "sha256:" + ("d" * 64)
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES ('RESET_FX_WATERMARKS', CAST(:payload AS JSON), 'PENDING', 'corr-claim-fx')
            """
        ),
        {
            "payload": (
                '{"from_currency":"USD","to_currency":"CHF",'
                '"earliest_impacted_date":"2025-01-03",'
                '"generated_at":"2025-01-08T00:00:00+00:00",'
                f'"content_hash":"{content_hash}",'
                '"extension":1e999999999999999999999999999999999999999}'
            )
        },
    )
    await async_db_session.commit()

    claimed = await ReprocessingJobRepository(async_db_session).find_and_claim_jobs(
        "RESET_FX_WATERMARKS",
        batch_size=1,
    )
    await async_db_session.commit()

    assert len(claimed) == 1
    assert claimed[0].payload == {
        "from_currency": "USD",
        "to_currency": "CHF",
        "earliest_impacted_date": "2025-01-03",
        "generated_at": "2025-01-08T00:00:00+00:00",
        "content_hash": content_hash,
    }
    assert claimed[0].correlation_id == "corr-claim-fx"


async def test_reset_staging_coalesces_oversized_extension_through_safe_return(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    oversized_integer = "8" * 5_000
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (
                job_type, payload, status, correlation_id
            ) VALUES (
                'RESET_WATERMARKS', CAST(:payload AS JSON), 'PENDING', 'corr-original'
            )
            """
        ),
        {
            "payload": (
                '{"security_id":"S-STAGE-LARGE",'
                '"earliest_impacted_date":"2025-01-07",'
                f'"extension":{oversized_integer}}}'
            )
        },
    )
    await async_db_session.commit()

    result = await ReprocessingJobRepository(async_db_session).stage_reset_watermarks_job(
        security_id="S-STAGE-LARGE",
        earliest_impacted_date=date(2025, 1, 5),
        correlation_id="corr-correction",
    )
    await async_db_session.commit()

    assert result.outcome is ResetWatermarksStageOutcome.COALESCED_PENDING
    assert result.job.payload["earliest_impacted_date"] == "2025-01-05"
    assert str(result.job.payload["extension"]) == oversized_integer
    assert result.job.correlation_id == "corr-correction"
    persisted = (
        await async_db_session.execute(
            text(
                """
                SELECT count(*) AS row_count,
                       min(payload->>'earliest_impacted_date') AS earliest_date,
                       bool_and(payload::text LIKE '%"extension"%') AS extension_preserved
                FROM reprocessing_jobs
                WHERE status = 'PENDING'
                  AND job_type = 'RESET_WATERMARKS'
                  AND payload->>'security_id' = 'S-STAGE-LARGE'
                """
            )
        )
    ).one()
    assert persisted.row_count == 1
    assert persisted.earliest_date == "2025-01-05"
    assert persisted.extension_preserved is True


async def test_find_and_claim_jobs_does_not_cast_unrepresentable_reset_date(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES
              (
                'RESET_WATERMARKS',
                CAST(
                  '{"security_id":"S-WEEK","earliest_impacted_date":"2025-W01-2"}'
                  AS JSON
                ),
                'PENDING'
              ),
              (
                'RESET_WATERMARKS',
                CAST(
                  '{"security_id":"S-VALID","earliest_impacted_date":"2025-01-05"}'
                  AS JSON
                ),
                'PENDING'
              )
            """
        )
    )
    await async_db_session.commit()

    claimed = await ReprocessingJobRepository(async_db_session).find_and_claim_jobs(
        "RESET_WATERMARKS",
        batch_size=2,
    )
    await async_db_session.commit()

    assert {job.payload["security_id"] for job in claimed} == {"S-WEEK", "S-VALID"}


async def test_find_and_claim_jobs_keeps_other_job_types_untouched(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN duplicate-looking payloads for a non-RESET_WATERMARKS job type
    WHEN the generic claim path runs
    THEN the repository should not apply reset-watermarks normalization logic.
    """
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES
              (
                'OTHER_JOB',
                '{"security_id":"S1","earliest_impacted_date":"2025-01-07"}',
                'PENDING'
              ),
              (
                'OTHER_JOB',
                '{"security_id":"S1","earliest_impacted_date":"2025-01-05"}',
                'PENDING'
              )
            """
        )
    )
    await async_db_session.commit()

    repository = ReprocessingJobRepository(async_db_session)

    claimed = await repository.find_and_claim_jobs("OTHER_JOB", batch_size=10)
    await async_db_session.commit()

    assert len(claimed) == 2
    all_other_jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(ReprocessingJob.job_type == "OTHER_JOB")
            )
        )
        .scalars()
        .all()
    )
    assert len(all_other_jobs) == 2


async def test_pending_reset_watermarks_uniqueness_is_enforced_by_db(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN a pending RESET_WATERMARKS job already exists for a security
    WHEN a second pending RESET_WATERMARKS row for the same security is inserted directly
    THEN the database should reject it via the partial unique index.
    """
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status)
            VALUES (
              'RESET_WATERMARKS',
              '{"security_id":"S1","earliest_impacted_date":"2025-01-07"}',
              'PENDING'
            )
            """
        )
    )
    await async_db_session.commit()

    with pytest.raises(IntegrityError):
        await async_db_session.execute(
            text(
                """
                INSERT INTO reprocessing_jobs (job_type, payload, status)
                VALUES (
                  'RESET_WATERMARKS',
                  '{"security_id":"S1","earliest_impacted_date":"2025-01-05"}',
                  'PENDING'
                )
                """
            )
        )
        await async_db_session.commit()

    await async_db_session.rollback()


async def test_create_job_coalesces_pending_reset_watermarks_in_db(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN repeated repository create_job calls for the same security
    WHEN RESET_WATERMARKS work is created with a later then earlier impacted date
    THEN one pending row should remain and it should preserve the earliest date.
    """
    repository = ReprocessingJobRepository(async_db_session)

    first = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S1", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-late",
    )
    second = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S1", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-early",
    )
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(
                    ReprocessingJob.job_type == "RESET_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                    text("payload->>'security_id' = 'S1'"),
                )
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )

    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0].payload["security_id"] == "S1"
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[0].correlation_id == "corr-early"


async def test_create_job_backfills_missing_correlation_for_same_impacted_date(
    clean_db, async_db_session: AsyncSession
):
    repository = ReprocessingJobRepository(async_db_session)

    first = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
        correlation_id=None,
    )
    second = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-fill",
    )
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(
                    ReprocessingJob.job_type == "RESET_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                    text("payload->>'security_id' = 'S2'"),
                )
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )

    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[0].correlation_id == "corr-fill"
    assert rows[0].correlation_missing_reason is None
    assert rows[0].alternate_lookup_key is None


async def test_create_job_records_missing_correlation_diagnostics(
    clean_db, async_db_session: AsyncSession
):
    repository = ReprocessingJobRepository(async_db_session)

    job = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S9", "earliest_impacted_date": "2025-01-05"},
        correlation_id=None,
    )
    await async_db_session.commit()

    persisted = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(ReprocessingJob.id == job.id)
            )
        )
        .scalars()
        .one()
    )

    assert persisted.correlation_id is None
    assert persisted.correlation_missing_reason == "correlation_id_not_supplied"
    assert persisted.alternate_lookup_key == (
        "reprocessing_job|earliest_impacted_date=2025-01-05|job_type=RESET_WATERMARKS|"
        "security_id=S9"
    )


async def test_create_job_preserves_existing_correlation_when_earlier_date_has_none(
    clean_db, async_db_session: AsyncSession
):
    repository = ReprocessingJobRepository(async_db_session)

    first = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S3", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-existing",
    )
    second = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S3", "earliest_impacted_date": "2025-01-05"},
        correlation_id=None,
    )
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(
                    ReprocessingJob.job_type == "RESET_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                    text("payload->>'security_id' = 'S3'"),
                )
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )

    assert first.id == second.id
    assert len(rows) == 1
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[0].correlation_id == "corr-existing"


@pytest.mark.parametrize(
    ("claimed_date", "sibling_date", "expected_date", "expected_correlation"),
    [
        ("2025-01-05", "2025-01-07", "2025-01-05", "corr-claimed"),
        ("2025-01-07", "2025-01-05", "2025-01-05", "corr-sibling"),
        ("2025-01-05", "2025-01-05", "2025-01-05", "corr-sibling"),
    ],
)
async def test_owned_reset_requeue_coalesces_pending_sibling_without_narrowing_boundary(
    clean_db,
    async_db_session: AsyncSession,
    claimed_date: str,
    sibling_date: str,
    expected_date: str,
    expected_correlation: str,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-OWNED", "earliest_impacted_date": claimed_date},
        correlation_id="corr-claimed",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-OWNED", "earliest_impacted_date": sibling_date},
        correlation_id="corr-sibling",
    )
    await async_db_session.commit()

    outcome = await repository.requeue_owned_effective_dated_job(
        claimed.id,
        lease_token=claimed.lease_token,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    assert [row.status for row in rows] == ["COMPLETE", "PENDING"]
    assert rows[1].payload["earliest_impacted_date"] == expected_date
    assert rows[1].correlation_id == expected_correlation
    assert rows[0].lease_token is None
    assert rows[0].lease_expires_at is None


async def test_owned_and_stale_recovery_coalesce_oversized_pending_siblings(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    oversized_integer = "9" * 5_000

    async def claim_then_insert_sibling(
        security_id: str,
        *,
        excluded_job_ids: tuple[int, ...] = (),
    ):
        await repository.stage_reset_watermarks_job(
            security_id=security_id,
            earliest_impacted_date=date(2025, 1, 7),
            correlation_id=f"corr-{security_id}-claimed",
        )
        await async_db_session.commit()
        claimed = (
            await repository.find_and_claim_jobs(
                "RESET_WATERMARKS",
                batch_size=1,
                excluded_job_ids=excluded_job_ids,
            )
        )[0]
        await async_db_session.commit()
        sibling_id = (
            await async_db_session.execute(
                text(
                    """
                INSERT INTO reprocessing_jobs (
                    job_type, payload, status, correlation_id
                ) VALUES (
                    'RESET_WATERMARKS', CAST(:payload AS JSON), 'PENDING', :correlation_id
                )
                RETURNING id
                """
                ),
                {
                    "payload": (
                        f'{{"security_id":"{security_id}",'
                        '"earliest_impacted_date":"2025-01-05",'
                        f'"extension":{oversized_integer}}}'
                    ),
                    "correlation_id": f"corr-{security_id}-sibling",
                },
            )
        ).scalar_one()
        await async_db_session.commit()
        return claimed, sibling_id

    owned, owned_sibling_id = await claim_then_insert_sibling("S-OWNED-LARGE")
    assert (
        await repository.requeue_owned_effective_dated_job(
            owned.id,
            lease_token=owned.lease_token,
        )
        is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    )
    await async_db_session.commit()

    stale, _ = await claim_then_insert_sibling(
        "S-STALE-LARGE",
        excluded_job_ids=(owned_sibling_id,),
    )
    await async_db_session.execute(
        update(ReprocessingJob)
        .where(ReprocessingJob.id == stale.id)
        .values(lease_expires_at=func.clock_timestamp() - text("INTERVAL '1 second'"))
    )
    await async_db_session.commit()
    assert await repository.find_and_reset_stale_jobs(max_attempts=5) == 1
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                text(
                    """
                SELECT payload->>'security_id' AS security_id,
                       status,
                       payload->>'earliest_impacted_date' AS earliest_date,
                       correlation_id,
                       payload::text LIKE '%"extension"%' AS extension_preserved
                FROM reprocessing_jobs
                WHERE payload->>'security_id' IN ('S-OWNED-LARGE', 'S-STALE-LARGE')
                ORDER BY security_id, id
                """
                )
            )
        )
        .mappings()
        .all()
    )
    assert [(row["security_id"], row["status"]) for row in rows] == [
        ("S-OWNED-LARGE", "COMPLETE"),
        ("S-OWNED-LARGE", "PENDING"),
        ("S-STALE-LARGE", "COMPLETE"),
        ("S-STALE-LARGE", "PENDING"),
    ]
    pending_rows = [row for row in rows if row["status"] == "PENDING"]
    assert all(row["earliest_date"] == "2025-01-05" for row in pending_rows)
    assert all(row["extension_preserved"] is True for row in pending_rows)
    assert {row["correlation_id"] for row in pending_rows} == {
        "corr-S-OWNED-LARGE-sibling",
        "corr-S-STALE-LARGE-sibling",
    }


async def test_owned_reset_requeue_quarantines_normalized_legacy_sibling(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "BOND-PADDED", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-claimed",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    async_db_session.add(
        ReprocessingJob(
            job_type="RESET_WATERMARKS",
            payload={
                "security_id": "\tBOND-PADDED",
                "earliest_impacted_date": "2025-01-05",
            },
            status="PENDING",
            correlation_id="corr-legacy-padded",
        )
    )
    await async_db_session.commit()

    outcome = await repository.requeue_owned_effective_dated_job(
        claimed.id,
        lease_token=claimed.lease_token,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (await async_db_session.execute(select(ReprocessingJob).order_by(ReprocessingJob.id.asc())))
        .scalars()
        .all()
    )
    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    assert [row.status for row in rows] == ["COMPLETE", "FAILED", "PENDING"]
    assert rows[1].failure_reason == (
        "invalid_reset_watermarks_job_payload: superseded during valid replay staging"
    )
    assert rows[1].payload["security_id"] == "\tBOND-PADDED"
    assert rows[2].payload == {
        "security_id": "BOND-PADDED",
        "earliest_impacted_date": "2025-01-05",
    }
    assert rows[2].correlation_id == "corr-claimed"


async def test_owned_reset_requeue_preserves_sibling_claimed_after_scan(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "OWNED-RACE", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-owned-race",
    )
    await async_db_session.commit()
    owned = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    sibling_id = await async_db_session.scalar(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_WATERMARKS', CAST(:payload AS json), 'PENDING', 'corr-sibling-race'
            )
            RETURNING id
            """
        ),
        {"payload": ('{"security_id":" OWNED-RACE ","earliest_impacted_date":"2025-01-03"}')},
    )
    assert sibling_id is not None
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    scan_completed = asyncio.Event()
    allow_row_lock = asyncio.Event()
    requeue_applied = asyncio.Event()
    allow_requeue_commit = asyncio.Event()
    original_lock = payload_integrity._lock_scanned_replay_rows
    first_lock = True

    async def pause_first_lock_after_scan(
        db: AsyncSession,
        *,
        candidate_ids: list[int],
        preserve_candidate_ids: list[int],
        job_type: str,
    ):
        nonlocal first_lock
        if first_lock:
            first_lock = False
            scan_completed.set()
            await allow_row_lock.wait()
        return await original_lock(
            db,
            candidate_ids=candidate_ids,
            preserve_candidate_ids=preserve_candidate_ids,
            job_type=job_type,
        )

    async def requeue_owned():
        async with session_factory() as requeue_session, requeue_session.begin():
            outcome = await ReprocessingJobRepository(
                requeue_session
            ).requeue_owned_effective_dated_job(
                owned.id,
                lease_token=owned.lease_token,
            )
            requeue_applied.set()
            await allow_requeue_commit.wait()
            return outcome

    with patch.object(
        payload_integrity,
        "_lock_scanned_replay_rows",
        side_effect=pause_first_lock_after_scan,
    ):
        requeue_task = asyncio.create_task(requeue_owned())
        try:
            await asyncio.wait_for(scan_completed.wait(), timeout=5)
            async with session_factory() as claimant_session, claimant_session.begin():
                claimed = await ReprocessingJobRepository(claimant_session).find_and_claim_jobs(
                    "RESET_WATERMARKS",
                    batch_size=1,
                    lease_owner="sibling-race-worker",
                    normalize_reset_watermark_duplicates=False,
                )
                assert [job.id for job in claimed] == [sibling_id]
            allow_row_lock.set()
            await asyncio.wait_for(requeue_applied.wait(), timeout=5)
            async with session_factory() as renewal_session, renewal_session.begin():
                renewal = await asyncio.wait_for(
                    renewal_session.execute(
                        update(ReprocessingJob)
                        .where(
                            ReprocessingJob.id == sibling_id,
                            ReprocessingJob.status == "PROCESSING",
                            ReprocessingJob.lease_token == claimed[0].lease_token,
                        )
                        .values(
                            lease_expires_at=func.clock_timestamp() + text("INTERVAL '30 minutes'")
                        )
                    ),
                    timeout=5,
                )
                assert renewal.rowcount == 1
            allow_requeue_commit.set()
            outcome = await asyncio.wait_for(requeue_task, timeout=5)
        finally:
            allow_row_lock.set()
            allow_requeue_commit.set()
            if not requeue_task.done():
                requeue_task.cancel()
                await asyncio.gather(requeue_task, return_exceptions=True)

    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    async with session_factory() as evidence_session:
        rows = (
            (
                await evidence_session.execute(
                    select(ReprocessingJob)
                    .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                    .order_by(ReprocessingJob.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert [row.status for row in rows] == ["COMPLETE", "PROCESSING", "PENDING"]
    assert rows[1].id == sibling_id
    assert rows[1].lease_owner == "sibling-race-worker"
    assert rows[2].payload == {
        "security_id": "OWNED-RACE",
        "earliest_impacted_date": "2025-01-03",
    }


async def test_owned_fx_requeue_preserves_sibling_boundary_terminalized_after_scan(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    owned_hash = "sha256:" + ("a" * 64)
    await repository.stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="SGD",
        earliest_impacted_date=date(2025, 1, 7),
        content_hash=owned_hash,
        generated_at=datetime(2025, 1, 7, tzinfo=timezone.utc),
        correlation_id="corr-owned-fx-race",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )
    await async_db_session.commit()
    owned = (await repository.find_and_claim_jobs("RESET_FX_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    sibling_id = await async_db_session.scalar(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
                'RESET_FX_WATERMARKS', CAST(:payload AS json), 'PENDING', 'corr-fx-sibling-race'
            )
            RETURNING id
            """
        ),
        {
            "payload": (
                '{"from_currency":" USD ","to_currency":"SGD",'
                '"earliest_impacted_date":"2025-01-03",'
                '"generated_at":"invalid","content_hash":"legacy"}'
            )
        },
    )
    assert sibling_id is not None
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    scan_completed = asyncio.Event()
    allow_row_lock = asyncio.Event()
    original_lock = payload_integrity._lock_scanned_replay_rows
    first_lock = True

    async def pause_first_lock_after_scan(
        db: AsyncSession,
        *,
        candidate_ids: list[int],
        preserve_candidate_ids: list[int],
        job_type: str,
    ):
        nonlocal first_lock
        if first_lock:
            first_lock = False
            scan_completed.set()
            await allow_row_lock.wait()
        return await original_lock(
            db,
            candidate_ids=candidate_ids,
            preserve_candidate_ids=preserve_candidate_ids,
            job_type=job_type,
        )

    async def requeue_owned():
        async with session_factory() as requeue_session, requeue_session.begin():
            return await ReprocessingJobRepository(
                requeue_session
            ).requeue_owned_effective_dated_job(
                owned.id,
                lease_token=owned.lease_token,
            )

    with patch.object(
        payload_integrity,
        "_lock_scanned_replay_rows",
        side_effect=pause_first_lock_after_scan,
    ):
        requeue_task = asyncio.create_task(requeue_owned())
        try:
            await asyncio.wait_for(scan_completed.wait(), timeout=5)
            async with session_factory() as claimant_session, claimant_session.begin():
                claimant_repository = ReprocessingJobRepository(claimant_session)
                claimed = await claimant_repository.find_and_claim_jobs(
                    "RESET_FX_WATERMARKS",
                    batch_size=1,
                    lease_owner="fx-sibling-race-worker",
                )
                assert [job.id for job in claimed] == [sibling_id]
                assert (
                    await claimant_repository.update_job_status(
                        sibling_id,
                        "FAILED",
                        lease_token=claimed[0].lease_token,
                        failure_reason="invalid legacy FX replay payload",
                    )
                    is ReprocessingJobTransitionOutcome.APPLIED
                )
            allow_row_lock.set()
            outcome = await asyncio.wait_for(requeue_task, timeout=5)
        finally:
            allow_row_lock.set()
            if not requeue_task.done():
                requeue_task.cancel()
                await asyncio.gather(requeue_task, return_exceptions=True)

    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    async with session_factory() as evidence_session:
        rows = (
            (
                await evidence_session.execute(
                    select(ReprocessingJob)
                    .where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
                    .order_by(ReprocessingJob.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert [row.status for row in rows] == ["COMPLETE", "FAILED", "PENDING"]
    assert rows[1].id == sibling_id
    assert rows[2].payload["earliest_impacted_date"] == "2025-01-03"
    assert rows[2].payload["content_hash"] == owned_hash
    assert rows[2].correlation_id == "corr-owned-fx-race"


async def test_owned_reset_requeue_adopts_equal_boundary_sibling_lineage(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    payload = {"security_id": "EQUAL-LINEAGE", "earliest_impacted_date": "2025-01-03"}
    await repository.create_job("RESET_WATERMARKS", payload, correlation_id=None)
    await async_db_session.commit()
    owned = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    assert owned.correlation_id is None
    await async_db_session.commit()

    await repository.create_job(
        "RESET_WATERMARKS",
        payload,
        correlation_id="corr-equal-boundary-sibling",
    )
    await async_db_session.commit()
    sibling = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()

    outcome = await repository.requeue_owned_effective_dated_job(
        owned.id,
        lease_token=owned.lease_token,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    assert [row.status for row in rows] == ["COMPLETE", "PROCESSING", "PENDING"]
    assert rows[1].id == sibling.id
    assert rows[2].payload == payload
    assert rows[2].correlation_id == "corr-equal-boundary-sibling"
    assert rows[2].correlation_missing_reason is None
    assert rows[2].alternate_lookup_key is None


async def test_owned_fx_requeue_preserves_already_processing_sibling_boundary(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    owned_hash = "sha256:" + ("b" * 64)
    sibling_hash = "sha256:" + ("c" * 64)
    await repository.stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="CHF",
        earliest_impacted_date=date(2025, 1, 7),
        content_hash=owned_hash,
        generated_at=datetime(2025, 1, 7, tzinfo=timezone.utc),
        correlation_id="corr-owned-before-scan",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )
    await async_db_session.commit()
    owned = (await repository.find_and_claim_jobs("RESET_FX_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    sibling_id = await async_db_session.scalar(
        text(
            """
            INSERT INTO reprocessing_jobs (
                job_type, payload, status, attempt_count, correlation_id
            )
            VALUES (
                'RESET_FX_WATERMARKS', CAST(:payload AS json), 'PENDING', 4,
                'corr-processing-before-scan'
            )
            RETURNING id
            """
        ),
        {
            "payload": (
                '{"from_currency":"USD","to_currency":"CHF",'
                '"earliest_impacted_date":"2025-01-03",'
                f'"generated_at":"2025-01-08T00:00:00+00:00",'
                f'"content_hash":"{sibling_hash}",'
                '"extension":1e999999999999999999999999999999999999999}'
            )
        },
    )
    assert sibling_id is not None
    await async_db_session.commit()
    processing_sibling = (
        await repository.find_and_claim_jobs(
            "RESET_FX_WATERMARKS",
            batch_size=1,
            lease_owner="processing-before-scan-worker",
        )
    )[0]
    assert processing_sibling.id == sibling_id
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as requeue_session, requeue_session.begin():
        outcome = await ReprocessingJobRepository(
            requeue_session
        ).requeue_owned_effective_dated_job(
            owned.id,
            lease_token=owned.lease_token,
        )
        async with session_factory() as renewal_session, renewal_session.begin():
            renewal = await asyncio.wait_for(
                renewal_session.execute(
                    update(ReprocessingJob)
                    .where(
                        ReprocessingJob.id == sibling_id,
                        ReprocessingJob.status == "PROCESSING",
                        ReprocessingJob.lease_token == processing_sibling.lease_token,
                    )
                    .values(lease_expires_at=func.clock_timestamp() + text("INTERVAL '30 minutes'"))
                ),
                timeout=5,
            )
            assert renewal.rowcount == 1
    async_db_session.expire_all()

    rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    assert [row.status for row in rows] == ["COMPLETE", "PROCESSING", "PENDING"]
    assert rows[1].id == sibling_id
    assert rows[1].lease_token == processing_sibling.lease_token
    assert rows[1].attempt_count == 5
    assert rows[2].payload["earliest_impacted_date"] == "2025-01-03"
    assert rows[2].payload["content_hash"] == sibling_hash
    assert rows[2].attempt_count == 5
    assert rows[2].correlation_id == "corr-processing-before-scan"


@pytest.mark.parametrize(
    ("security_id", "poisoned_security_id_json"),
    (("123", "123"), ("[123]", "[123]"), ("1e2", "1e2")),
)
async def test_owned_reset_requeue_quarantines_only_matching_jsonb_unrepresentable_sibling(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
    security_id: str,
    poisoned_security_id_json: str,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": security_id, "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-claimed",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
              'RESET_WATERMARKS',
              CAST(:payload AS JSON),
              'PENDING',
              'corr-jsonb-unrepresentable'
            )
            """
        ),
        {
            "payload": (
                f'{{"security_id":{poisoned_security_id_json},'
                '"earliest_impacted_date":"2025-01-07",'
                '"legacy_number":1e1000000}'
            )
        },
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
              'RESET_WATERMARKS',
              CAST(:payload AS JSON),
              'PENDING',
              'corr-unrelated-jsonb-unrepresentable'
            )
            """
        ),
        {
            "payload": (
                '{"security_id":"OTHER-BOND",'
                '"earliest_impacted_date":"2025-01-01",'
                '"legacy_number":1e1000000}'
            )
        },
    )
    await async_db_session.commit()

    outcome = await repository.requeue_owned_effective_dated_job(
        claimed.id,
        lease_token=claimed.lease_token,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (await async_db_session.execute(select(ReprocessingJob).order_by(ReprocessingJob.id.asc())))
        .scalars()
        .all()
    )
    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    assert [row.status for row in rows] == ["COMPLETE", "FAILED", "PENDING", "PENDING"]
    assert rows[2].correlation_id == "corr-unrelated-jsonb-unrepresentable"
    assert rows[2].failure_reason is None
    assert rows[3].payload == {
        "security_id": security_id,
        "earliest_impacted_date": "2025-01-05",
    }
    assert rows[1].failure_reason == (
        "invalid_reset_watermarks_job_payload: superseded during valid replay staging"
    )


async def test_reset_quarantine_does_not_lock_unrelated_jsonb_poison(
    clean_db,
    async_db_session: AsyncSession,
    predecessor_reprocessing_payload_schema,
) -> None:
    matching_result = await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
              'RESET_WATERMARKS',
              CAST(:payload AS JSON),
              'PENDING',
              'corr-matching-lock-probe'
            )
            RETURNING id
            """
        ),
        {
            "payload": (
                '{"security_id":"LOCK-PROBE",'
                '"earliest_impacted_date":"2025-01-07",'
                '"legacy_number":1e1000000}'
            )
        },
    )
    unrelated_result = await async_db_session.execute(
        text(
            """
            INSERT INTO reprocessing_jobs (job_type, payload, status, correlation_id)
            VALUES (
              'RESET_WATERMARKS',
              CAST(:payload AS JSON),
              'PENDING',
              'corr-unrelated-lock-probe'
            )
            RETURNING id
            """
        ),
        {
            "payload": (
                '{"security_id":"OTHER-BOND",'
                '"earliest_impacted_date":"2025-01-01",'
                '"legacy_number":1e1000000}'
            )
        },
    )
    matching_id = int(matching_result.scalar_one())
    unrelated_id = int(unrelated_result.scalar_one())
    await async_db_session.commit()

    repository = ReprocessingJobRepository(async_db_session)
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as unrelated_owner:
        await unrelated_owner.execute(
            select(ReprocessingJob).where(ReprocessingJob.id == unrelated_id).with_for_update()
        )
        earliest = await asyncio.wait_for(
            repository._quarantine_malformed_pending_reset_watermarks(security_id="LOCK-PROBE"),
            timeout=5,
        )
        await async_db_session.commit()

    matching = await async_db_session.get(ReprocessingJob, matching_id)
    unrelated = await async_db_session.get(ReprocessingJob, unrelated_id)
    assert earliest == date(2025, 1, 7)
    assert matching is not None and matching.status == "FAILED"
    assert unrelated is not None and unrelated.status == "PENDING"


async def test_owned_reset_requeue_without_sibling_reuses_claimed_row(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    staged = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-DIRECT", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-direct",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()

    outcome = await repository.requeue_owned_effective_dated_job(
        claimed.id,
        lease_token=claimed.lease_token,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (await async_db_session.execute(select(ReprocessingJob))).scalars().all()
    assert outcome is ReprocessingJobTransitionOutcome.REQUEUED
    assert len(rows) == 1
    assert rows[0].id == staged.id
    assert rows[0].status == "PENDING"
    assert rows[0].lease_token is None


async def test_owned_reset_requeue_rejects_stale_token_without_touching_sibling(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-FENCED", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-claimed",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-FENCED", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-sibling",
    )
    await async_db_session.commit()

    outcome = await repository.requeue_owned_effective_dated_job(
        claimed.id,
        lease_token="f" * 32,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (await async_db_session.execute(select(ReprocessingJob).order_by(ReprocessingJob.id.asc())))
        .scalars()
        .all()
    )
    assert outcome is ReprocessingJobTransitionOutcome.CLAIM_MISMATCH
    assert rows[0].status == "PROCESSING"
    assert rows[0].lease_token == claimed.lease_token
    assert rows[1].status == "PENDING"
    assert rows[1].payload["earliest_impacted_date"] == "2025-01-05"


async def test_owned_fx_requeue_preserves_earliest_date_and_latest_source_lineage(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="SGD",
        earliest_impacted_date=date(2025, 1, 7),
        content_hash="sha256:" + ("a" * 64),
        generated_at=datetime(2025, 1, 7, tzinfo=timezone.utc),
        correlation_id="corr-claimed",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_FX_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    await repository.stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="SGD",
        earliest_impacted_date=date(2025, 1, 5),
        content_hash="sha256:" + ("b" * 64),
        generated_at=datetime(2025, 1, 8, tzinfo=timezone.utc),
        correlation_id="corr-sibling",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )
    await async_db_session.commit()

    outcome = await repository.requeue_owned_effective_dated_job(
        claimed.id,
        lease_token=claimed.lease_token,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (
        (await async_db_session.execute(select(ReprocessingJob).order_by(ReprocessingJob.id.asc())))
        .scalars()
        .all()
    )
    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    assert [row.status for row in rows] == ["COMPLETE", "PENDING"]
    assert rows[1].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[1].payload["content_hash"] == "sha256:" + ("b" * 64)
    assert rows[1].payload["generated_at"] == "2025-01-08T00:00:00+00:00"
    assert rows[1].correlation_id == "corr-sibling"


async def test_owned_requeue_outer_rollback_restores_claim_and_sibling(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-ROLLBACK", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-claimed",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-ROLLBACK", "earliest_impacted_date": "2025-01-09"},
        correlation_id="corr-sibling",
    )
    await async_db_session.commit()

    assert (
        await repository.requeue_owned_effective_dated_job(
            claimed.id,
            lease_token=claimed.lease_token,
        )
        is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    )
    await async_db_session.rollback()
    async_db_session.expire_all()

    rows = (
        (await async_db_session.execute(select(ReprocessingJob).order_by(ReprocessingJob.id.asc())))
        .scalars()
        .all()
    )
    assert [row.status for row in rows] == ["PROCESSING", "PENDING"]
    assert rows[0].lease_token == claimed.lease_token
    assert rows[1].payload["earliest_impacted_date"] == "2025-01-09"
    assert rows[1].correlation_id == "corr-sibling"


async def test_owned_requeue_replay_is_idempotent_after_direct_requeue(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-REPLAY", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-replay",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()

    assert (
        await repository.requeue_owned_effective_dated_job(
            claimed.id,
            lease_token=claimed.lease_token,
        )
        is ReprocessingJobTransitionOutcome.REQUEUED
    )
    await async_db_session.commit()
    repeated = await repository.requeue_owned_effective_dated_job(
        claimed.id,
        lease_token=claimed.lease_token,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    rows = (await async_db_session.execute(select(ReprocessingJob))).scalars().all()
    assert repeated is ReprocessingJobTransitionOutcome.NOT_PROCESSING
    assert len(rows) == 1
    assert rows[0].status == "PENDING"
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"


async def test_concurrent_staging_waits_for_owned_requeue_identity_lock(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-CONCURRENT", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-claimed",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def stage_earlier_sibling() -> None:
        async with session_factory() as sibling_session, sibling_session.begin():
            await ReprocessingJobRepository(sibling_session).create_job(
                "RESET_WATERMARKS",
                {
                    "security_id": "S-CONCURRENT",
                    "earliest_impacted_date": "2025-01-05",
                },
                correlation_id="corr-concurrent",
            )

    stage_task = None
    async with session_factory() as requeue_session, requeue_session.begin():
        await requeue_session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('RESET_WATERMARKS|12:S-CONCURRENT', 0))"
            )
        )
        stage_task = asyncio.create_task(stage_earlier_sibling())
        await asyncio.sleep(0.1)
        assert not stage_task.done()
        outcome = await ReprocessingJobRepository(
            requeue_session
        ).requeue_owned_effective_dated_job(
            claimed.id,
            lease_token=claimed.lease_token,
        )
        assert outcome is ReprocessingJobTransitionOutcome.REQUEUED
    await stage_task

    async_db_session.expire_all()
    rows = (
        (await async_db_session.execute(select(ReprocessingJob).order_by(ReprocessingJob.id.asc())))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "PENDING"
    assert rows[0].payload["earliest_impacted_date"] == "2025-01-05"
    assert rows[0].correlation_id == "corr-concurrent"


async def test_stale_recovery_waits_for_owned_requeue_without_lock_inversion(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = ReprocessingJobRepository(async_db_session)
    await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "S-STALE-RACE", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-stale-race",
    )
    await async_db_session.commit()
    claimed = (await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1))[0]
    await async_db_session.execute(
        text(
            """
            UPDATE reprocessing_jobs
            SET lease_expires_at = clock_timestamp() - interval '1 second'
            WHERE id = :job_id
            """
        ),
        {"job_id": claimed.id},
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    recovery_pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def recover_stale_job() -> int:
        async with session_factory() as recovery_session, recovery_session.begin():
            recovery_pid = int(await recovery_session.scalar(text("SELECT pg_backend_pid()")))
            recovery_pid_ready.set_result(recovery_pid)
            return await ReprocessingJobRepository(recovery_session).find_and_reset_stale_jobs(
                max_attempts=3
            )

    recovery_task = None
    async with session_factory() as requeue_session, requeue_session.begin():
        await requeue_session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('RESET_WATERMARKS|12:S-STALE-RACE', 0))"
            )
        )
        recovery_task = asyncio.create_task(recover_stale_job())
        recovery_pid = await asyncio.wait_for(recovery_pid_ready, timeout=5)
        await _wait_for_backend_advisory_lock(
            session_factory=session_factory,
            backend_pid=recovery_pid,
        )
        assert not recovery_task.done()
        await requeue_session.execute(
            text(
                """
                UPDATE reprocessing_jobs
                SET lease_expires_at = clock_timestamp() + interval '5 minutes'
                WHERE id = :job_id
                """
            ),
            {"job_id": claimed.id},
        )
        outcome = await ReprocessingJobRepository(
            requeue_session
        ).requeue_owned_effective_dated_job(
            claimed.id,
            lease_token=claimed.lease_token,
        )
        assert outcome is ReprocessingJobTransitionOutcome.REQUEUED

    assert recovery_task is not None
    assert await asyncio.wait_for(recovery_task, timeout=5) == 0
    async_db_session.expire_all()
    row = (
        await async_db_session.execute(
            select(ReprocessingJob).where(ReprocessingJob.id == claimed.id)
        )
    ).scalar_one()
    assert row.status == "PENDING"
    assert row.failure_reason is None
    assert row.payload["earliest_impacted_date"] == "2025-01-07"


async def test_concurrent_stale_recovery_claims_disjoint_bounded_cohorts(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    job_count = POSTGRES_STATEMENT_ROW_LIMIT + 1
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="LEASE_LIFECYCLE_PROOF",
                payload={"sequence": sequence},
                status="PROCESSING",
                attempt_count=1,
                lease_owner=f"stale-worker-{sequence}",
                lease_token=f"{sequence:032x}",
                lease_expires_at=stale_time,
            )
            for sequence in range(job_count)
        ]
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    before_commit = asyncio.Barrier(2)

    async def recover_cohort() -> tuple[int, set[int]]:
        async with session_factory() as session, session.begin():
            recovered_count = await ReprocessingJobRepository(session).find_and_reset_stale_jobs(
                max_attempts=3
            )
            recovered_ids = set(
                (
                    await session.scalars(
                        select(ReprocessingJob.id).where(ReprocessingJob.status == "PENDING")
                    )
                ).all()
            )
            await before_commit.wait()
            return recovered_count, recovered_ids

    recovered_cohorts = await asyncio.wait_for(
        asyncio.gather(recover_cohort(), recover_cohort()),
        timeout=30,
    )

    recovered_counts = [count for count, _ in recovered_cohorts]
    first_ids, second_ids = (ids for _, ids in recovered_cohorts)
    assert sorted(recovered_counts) == [1, POSTGRES_STATEMENT_ROW_LIMIT]
    assert first_ids.isdisjoint(second_ids)
    assert len(first_ids | second_ids) == job_count
    async_db_session.expire_all()
    pending_count = int(
        await async_db_session.scalar(
            select(func.count())
            .select_from(ReprocessingJob)
            .where(ReprocessingJob.status == "PENDING")
        )
        or 0
    )
    assert pending_count == job_count


async def test_find_and_reset_stale_jobs_does_not_overwrite_completed_rows(
    clean_db, async_db_session: AsyncSession
):
    job = ReprocessingJob(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S4", "earliest_impacted_date": "2025-01-05"},
        status="PROCESSING",
        lease_owner="concurrent-completion-worker",
        lease_token="2" * 32,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    async_db_session.add(job)
    await async_db_session.flush()
    await async_db_session.execute(
        text(
            """
            UPDATE reprocessing_jobs
            SET lease_expires_at = clock_timestamp() - interval '20 minutes'
            WHERE id = :job_id
            """
        ),
        {"job_id": job.id},
    )
    await async_db_session.commit()

    concurrent_session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with concurrent_session_factory() as session:
        await session.execute(
            update(ReprocessingJob)
            .where(ReprocessingJob.id == job.id)
            .values(
                status="COMPLETE",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
            )
        )
        await session.commit()

    reset_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        max_attempts=3
    )
    await async_db_session.commit()

    assert reset_count == 0

    async with concurrent_session_factory() as persisted_session:
        persisted = (
            (
                await persisted_session.execute(
                    select(ReprocessingJob).where(ReprocessingJob.id == job.id)
                )
            )
            .scalars()
            .one()
        )
    assert persisted.status == "COMPLETE"


async def test_find_and_claim_jobs_does_not_double_claim_under_concurrency(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        ReprocessingJob(
            job_type="RESET_WATERMARKS",
            payload={"security_id": "S5", "earliest_impacted_date": "2025-01-05"},
            status="PENDING",
        )
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def claim_one():
        async with session_factory() as session:
            repository = ReprocessingJobRepository(session)
            claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1)
            await session.commit()
            return claimed

    first_claim, second_claim = await asyncio.gather(claim_one(), claim_one())
    all_claimed = [*first_claim, *second_claim]

    assert len(all_claimed) == 1
    assert len({job.id for job in all_claimed}) == 1

    persisted_rows = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(persisted_rows) == 1
    assert persisted_rows[0].status == "PROCESSING"
    assert persisted_rows[0].attempt_count == 1


async def test_expired_claim_is_recovered_reclaimed_and_fences_late_terminal_write(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    pending = ReprocessingJob(
        job_type="LEASE_LIFECYCLE_PROOF",
        payload={"scope": "reprocessing-lease-lifecycle"},
        status="PENDING",
    )
    async_db_session.add(pending)
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with session_factory() as first_session, first_session.begin():
        first_claim = (
            await ReprocessingJobRepository(first_session).find_and_claim_jobs(
                "LEASE_LIFECYCLE_PROOF",
                batch_size=1,
                lease_owner="first-reprocessing-worker",
                lease_duration_seconds=900,
            )
        )[0]

    original_expiry = first_claim.lease_expires_at
    async with session_factory() as renewal_session, renewal_session.begin():
        assert (
            await ReprocessingJobRepository(renewal_session).renew_lease(
                first_claim.id,
                lease_token=first_claim.lease_token,
                lease_duration_seconds=1800,
            )
            is ReprocessingJobTransitionOutcome.APPLIED
        )
    async with session_factory() as renewed_read_session:
        renewed = await renewed_read_session.get(ReprocessingJob, first_claim.id)
        assert renewed is not None
        assert renewed.lease_expires_at > original_expiry

    async with session_factory() as expiry_session, expiry_session.begin():
        await expiry_session.execute(
            update(ReprocessingJob)
            .where(ReprocessingJob.id == first_claim.id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )

    async with session_factory() as recovery_session, recovery_session.begin():
        assert (
            await ReprocessingJobRepository(recovery_session).find_and_reset_stale_jobs(
                max_attempts=3
            )
            == 1
        )

    async with session_factory() as second_session, second_session.begin():
        second_claim = (
            await ReprocessingJobRepository(second_session).find_and_claim_jobs(
                "LEASE_LIFECYCLE_PROOF",
                batch_size=1,
                lease_owner="second-reprocessing-worker",
                lease_duration_seconds=900,
            )
        )[0]

    assert second_claim.id == first_claim.id
    assert second_claim.attempt_count == 2
    assert second_claim.lease_token != first_claim.lease_token

    async with session_factory() as late_session, late_session.begin():
        assert (
            await ReprocessingJobRepository(late_session).update_job_status(
                first_claim.id,
                "COMPLETE",
                lease_token=first_claim.lease_token,
            )
            is ReprocessingJobTransitionOutcome.CLAIM_MISMATCH
        )

    async with session_factory() as current_session, current_session.begin():
        assert (
            await ReprocessingJobRepository(current_session).update_job_status(
                second_claim.id,
                "COMPLETE",
                lease_token=second_claim.lease_token,
            )
            is ReprocessingJobTransitionOutcome.APPLIED
        )

    async_db_session.expire_all()
    persisted = await async_db_session.get(ReprocessingJob, first_claim.id)
    assert persisted is not None
    assert persisted.status == "COMPLETE"
    assert persisted.attempt_count == 2
    assert persisted.lease_owner is None
    assert persisted.lease_token is None
    assert persisted.lease_expires_at is None


async def test_worker_database_failure_isolated_from_sibling_and_failed_in_fresh_session(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """A PostgreSQL-aborted job transaction cannot poison its sibling or failure write."""

    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "FAIL-SECURITY",
                    "earliest_impacted_date": "2025-01-01",
                },
                status="PENDING",
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={
                    "security_id": "PASS-SECURITY",
                    "earliest_impacted_date": "2025-01-02",
                },
                status="PENDING",
            ),
        ]
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def session_provider():
        async with session_factory() as session:
            yield session

    class Valuations:
        async def find_portfolios_holding_security_on_date(self, *_args):
            return ["PORTFOLIO-1"]

        async def find_portfolios_first_holding_security_after_date(self, *_args):
            return []

    class PositionStates:
        def __init__(self, db):
            self.db = db

        async def update_watermarks_if_older(self, *, keys, new_watermark_date):
            del new_watermark_date
            if keys[0][1] == "FAIL-SECURITY":
                await self.db.execute(text("SELECT 1 / 0"))
            return len(keys)

    class FxRevaluations:
        async def claim_pending_jobs(self, *_args, **_kwargs):
            return []

    repositories = ReprocessingWorkerRepositoryFactory(
        reprocessing_job_repository_factory=ReprocessingJobRepository,
        position_state_repository_factory=PositionStates,
        valuation_repository_factory=lambda _db: Valuations(),
        fx_revaluation_repository_factory=lambda _db: FxRevaluations(),
    )
    worker = ReprocessingWorker(
        batch_size=2,
        session_provider=session_provider,
        repository_factory=repositories,
    )

    with patch(
        "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_worker_jobs_failed"
    ) as observe_failed:
        await worker._process_batch()

    async_db_session.expire_all()
    persisted = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(ReprocessingJob.job_type == "RESET_WATERMARKS")
            )
        )
        .scalars()
        .all()
    )
    jobs_by_security = {job.payload["security_id"]: job for job in persisted}
    failed = jobs_by_security["FAIL-SECURITY"]
    succeeded = jobs_by_security["PASS-SECURITY"]
    assert failed.status == "FAILED"
    assert failed.attempt_count == 1
    assert "division by zero" in failed.failure_reason
    assert succeeded.status == "COMPLETE"
    assert succeeded.attempt_count == 1
    observe_failed.assert_called_once_with("RESET_WATERMARKS")
