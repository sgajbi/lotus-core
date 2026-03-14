from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import FinancialReconciliationRun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.financial_reconciliation_service.app.repositories import (
    reconciliation_repository as reconciliation_repo,
)

pytestmark = pytest.mark.asyncio


async def test_create_run_deduplicates_concurrent_requests(
    clean_db, async_db_session: AsyncSession
):
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    dedupe_key = "auto:transaction_cashflow:P-CONC:2026-03-14:7"
    barrier_lock = asyncio.Lock()
    barrier_ready = asyncio.Event()
    barrier_count = 0

    async def create_one() -> tuple[str, bool]:
        nonlocal barrier_count
        async with session_factory() as session:
            repo = reconciliation_repo.ReconciliationRepository(session)
            original_get = repo.get_run_by_dedupe_key

            async def synchronized_get_run_by_dedupe_key(key: str):
                nonlocal barrier_count
                result = await original_get(key)
                async with barrier_lock:
                    barrier_count += 1
                    if barrier_count == 2:
                        barrier_ready.set()
                await barrier_ready.wait()
                return result

            repo.get_run_by_dedupe_key = synchronized_get_run_by_dedupe_key  # type: ignore[method-assign]
            run, created = await repo.create_run(
                reconciliation_type="transaction_cashflow",
                portfolio_id="P-CONC",
                business_date=date(2026, 3, 14),
                epoch=7,
                requested_by="system_pipeline",
                dedupe_key=dedupe_key,
                correlation_id="corr-conc",
                tolerance=Decimal("0.01"),
            )
            await session.commit()
            return run.run_id, created

    first, second = await asyncio.gather(create_one(), create_one())

    created_flags = sorted([first[1], second[1]])
    assert created_flags == [False, True]
    assert first[0] == second[0]

    async with session_factory() as verification_session:
        rows = (
            (
                await verification_session.execute(
                    select(FinancialReconciliationRun).where(
                        FinancialReconciliationRun.dedupe_key == dedupe_key
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].run_id == first[0]
