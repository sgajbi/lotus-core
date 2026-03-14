from __future__ import annotations

import asyncio
from datetime import date

import pytest
from portfolio_common.database_models import InstrumentReprocessingState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.valuation_orchestrator_service.app.repositories import (
    instrument_reprocessing_state_repository as instrument_reprocessing_state_repo,
)

pytestmark = pytest.mark.asyncio


async def test_upsert_state_keeps_earliest_impacted_date(clean_db, async_db_session: AsyncSession):
    """
    GIVEN repeated back-dated price events for the same security
    WHEN the trigger repository upserts the instrument reprocessing state
    THEN one row should remain and it should carry the earliest impacted date.
    """
    repo = instrument_reprocessing_state_repo.InstrumentReprocessingStateRepository(
        async_db_session
    )

    await repo.upsert_state("S-TRIGGER-1", date(2025, 8, 10), correlation_id="corr-10")
    await repo.upsert_state("S-TRIGGER-1", date(2025, 8, 8), correlation_id="corr-08")
    await repo.upsert_state("S-TRIGGER-1", date(2025, 8, 12), correlation_id="corr-12")
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(InstrumentReprocessingState).where(
                    InstrumentReprocessingState.security_id == "S-TRIGGER-1"
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(rows) == 1
    assert rows[0].earliest_impacted_date == date(2025, 8, 8)
    assert rows[0].correlation_id == "corr-08"


async def test_upsert_state_preserves_one_row_per_security(
    clean_db, async_db_session: AsyncSession
):
    repo = instrument_reprocessing_state_repo.InstrumentReprocessingStateRepository(
        async_db_session
    )

    await repo.upsert_state("S-TRIGGER-1", date(2025, 8, 10), correlation_id="corr-a")
    await repo.upsert_state("S-TRIGGER-2", date(2025, 8, 9), correlation_id="corr-b")
    await repo.upsert_state("S-TRIGGER-1", date(2025, 8, 7), correlation_id="corr-c")
    await async_db_session.commit()

    rows = (
        (
            await async_db_session.execute(
                select(InstrumentReprocessingState).order_by(
                    InstrumentReprocessingState.security_id.asc()
                )
            )
        )
        .scalars()
        .all()
    )

    assert [(row.security_id, row.earliest_impacted_date) for row in rows] == [
        ("S-TRIGGER-1", date(2025, 8, 7)),
        ("S-TRIGGER-2", date(2025, 8, 9)),
    ]
    assert [(row.security_id, row.correlation_id) for row in rows] == [
        ("S-TRIGGER-1", "corr-c"),
        ("S-TRIGGER-2", "corr-b"),
    ]


async def test_upsert_state_backfills_missing_correlation_for_same_impacted_date(
    clean_db, async_db_session: AsyncSession
):
    repo = instrument_reprocessing_state_repo.InstrumentReprocessingStateRepository(
        async_db_session
    )

    await repo.upsert_state("S-TRIGGER-3", date(2025, 8, 10), correlation_id=None)
    await repo.upsert_state("S-TRIGGER-3", date(2025, 8, 10), correlation_id="corr-fill")
    await async_db_session.commit()

    row = (
        (
            await async_db_session.execute(
                select(InstrumentReprocessingState).where(
                    InstrumentReprocessingState.security_id == "S-TRIGGER-3"
                )
            )
        )
        .scalars()
        .one()
    )

    assert row.earliest_impacted_date == date(2025, 8, 10)
    assert row.correlation_id == "corr-fill"


async def test_upsert_state_preserves_existing_correlation_when_earlier_event_has_none(
    clean_db, async_db_session: AsyncSession
):
    repo = instrument_reprocessing_state_repo.InstrumentReprocessingStateRepository(
        async_db_session
    )

    await repo.upsert_state("S-TRIGGER-4", date(2025, 8, 10), correlation_id="corr-10")
    await repo.upsert_state("S-TRIGGER-4", date(2025, 8, 8), correlation_id=None)
    await async_db_session.commit()

    row = (
        (
            await async_db_session.execute(
                select(InstrumentReprocessingState).where(
                    InstrumentReprocessingState.security_id == "S-TRIGGER-4"
                )
            )
        )
        .scalars()
        .one()
    )

    assert row.earliest_impacted_date == date(2025, 8, 8)
    assert row.correlation_id == "corr-10"


async def test_upsert_state_normalizes_sentinel_correlation(
    clean_db, async_db_session: AsyncSession
):
    repo = instrument_reprocessing_state_repo.InstrumentReprocessingStateRepository(
        async_db_session
    )

    await repo.upsert_state("S-TRIGGER-5", date(2025, 8, 10), correlation_id="<not-set>")
    await async_db_session.commit()

    row = (
        (
            await async_db_session.execute(
                select(InstrumentReprocessingState).where(
                    InstrumentReprocessingState.security_id == "S-TRIGGER-5"
                )
            )
        )
        .scalars()
        .one()
    )

    assert row.correlation_id is None


async def test_upsert_state_coalesces_concurrent_duplicate_arrivals(
    clean_db, async_db_session: AsyncSession
):
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    barrier_lock = asyncio.Lock()
    barrier_ready = asyncio.Event()
    barrier_count = 0

    async def upsert_one(price_date: date, correlation_id: str | None) -> None:
        nonlocal barrier_count
        async with session_factory() as session:
            repo = instrument_reprocessing_state_repo.InstrumentReprocessingStateRepository(session)
            original_execute = session.execute

            async def synchronized_execute(*args, **kwargs):
                nonlocal barrier_count
                async with barrier_lock:
                    barrier_count += 1
                    if barrier_count == 2:
                        barrier_ready.set()
                await barrier_ready.wait()
                return await original_execute(*args, **kwargs)

            session.execute = synchronized_execute
            await repo.upsert_state("S-TRIGGER-CONC", price_date, correlation_id=correlation_id)
            await session.commit()

    await asyncio.gather(
        upsert_one(date(2025, 8, 10), "corr-10"),
        upsert_one(date(2025, 8, 8), "corr-08"),
    )

    async with session_factory() as verification_session:
        rows = (
            (
                await verification_session.execute(
                    select(InstrumentReprocessingState).where(
                        InstrumentReprocessingState.security_id == "S-TRIGGER-CONC"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].earliest_impacted_date == date(2025, 8, 8)
    assert rows[0].correlation_id == "corr-08"
