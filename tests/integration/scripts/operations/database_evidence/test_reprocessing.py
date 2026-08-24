from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from portfolio_common.database_models import ReprocessingJob
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from scripts.operations.database_evidence.contract import load_hot_path_scenario_catalog
from scripts.operations.database_evidence.reprocessing import (
    measure_reprocessing_job_claim,
    measure_reprocessing_stale_recovery,
)
from scripts.operations.database_evidence.runtime_fragments import publish_requested_fragments

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")
REFERENCE_NOW = datetime(2020, 1, 1, 12, tzinfo=UTC)


async def _seed_reprocessing_jobs(session: AsyncSession, *, count: int) -> None:
    pending_count = count // 2
    batch_size = 1_000
    for start in range(0, count, batch_size):
        stop = min(start + batch_size, count)
        await session.execute(
            insert(ReprocessingJob),
            [
                {
                    "job_type": ("RESET_WATERMARKS" if sequence < pending_count else "OTHER_JOB"),
                    "payload": {
                        "security_id": f"PLAN-REPROCESS-{sequence:05d}",
                        "earliest_impacted_date": (
                            date(2025, 1, 1) + timedelta(days=sequence % 365)
                        ).isoformat(),
                    },
                    "status": "PENDING" if sequence < pending_count else "PROCESSING",
                    "attempt_count": 1,
                    "last_attempted_at": REFERENCE_NOW - timedelta(hours=2),
                    "created_at": REFERENCE_NOW - timedelta(days=2, seconds=sequence),
                    "updated_at": REFERENCE_NOW - timedelta(hours=1),
                    "lease_owner": (
                        None if sequence < pending_count else "hot-path-evidence-worker"
                    ),
                    "lease_token": None if sequence < pending_count else f"{sequence:032x}",
                    "lease_expires_at": (
                        None if sequence < pending_count else REFERENCE_NOW - timedelta(hours=1)
                    ),
                }
                for sequence in range(start, stop)
            ],
        )
    await session.commit()
    await session.execute(text("ANALYZE reprocessing_jobs"))
    await session.commit()


async def _reprocessing_authority_snapshot(
    session: AsyncSession,
) -> list[tuple[object, ...]]:
    rows = await session.execute(
        select(
            ReprocessingJob.id,
            ReprocessingJob.job_type,
            ReprocessingJob.payload,
            ReprocessingJob.status,
            ReprocessingJob.attempt_count,
            ReprocessingJob.last_attempted_at,
            ReprocessingJob.failure_reason,
            ReprocessingJob.lease_owner,
            ReprocessingJob.lease_token,
            ReprocessingJob.lease_expires_at,
            ReprocessingJob.created_at,
            ReprocessingJob.updated_at,
        ).order_by(ReprocessingJob.id)
    )
    return [tuple(row) for row in rows]


async def test_reprocessing_claim_and_stale_recovery_publish_rollback_safe_evidence(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    scenarios = load_hot_path_scenario_catalog(CATALOG_PATH).by_id()
    seed_cardinality = scenarios["reprocessing_job_claim"].seed_cardinality
    assert {
        scenarios["reprocessing_claim_normalization"].seed_cardinality,
        scenarios["reprocessing_stale_scan"].seed_cardinality,
        scenarios["reprocessing_stale_reset"].seed_cardinality,
    } == {seed_cardinality}
    await _seed_reprocessing_jobs(async_db_session, count=seed_cardinality)
    authority_before = await _reprocessing_authority_snapshot(async_db_session)
    stale_job_ids = tuple(int(row[0]) for row in authority_before if row[3] == "PROCESSING")[
        : scenarios["reprocessing_stale_reset"].max_root_actual_rows
    ]
    await async_db_session.rollback()

    normalization_result, claim_result = await measure_reprocessing_job_claim(
        async_db_session,
        normalization_scenario=scenarios["reprocessing_claim_normalization"],
        claim_scenario=scenarios["reprocessing_job_claim"],
    )
    stale_scan_result, stale_reset_result = await measure_reprocessing_stale_recovery(
        async_db_session,
        scan_scenario=scenarios["reprocessing_stale_scan"],
        reset_scenario=scenarios["reprocessing_stale_reset"],
        reset_job_ids=stale_job_ids,
    )
    publish_requested_fragments(
        (normalization_result, claim_result, stale_reset_result, stale_scan_result)
    )

    verification_sessions = async_sessionmaker(
        bind=async_db_session.bind,
        expire_on_commit=False,
    )
    async with verification_sessions() as verification_session:
        authority_after = await _reprocessing_authority_snapshot(verification_session)
    assert authority_after == authority_before
    assert len(authority_after) == seed_cardinality
