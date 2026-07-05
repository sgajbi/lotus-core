import asyncio

import pytest
from portfolio_common.database_models import ProcessedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
    pytest.mark.resilience,
]


async def test_same_idempotency_key_concurrent_claim_creates_one_processed_event(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    workers_ready = asyncio.Event()
    release_workers = asyncio.Event()
    ready_count = 0

    async def claim_once(correlation_id: str) -> bool:
        nonlocal ready_count
        ready_count += 1
        if ready_count == 2:
            workers_ready.set()
        await release_workers.wait()

        async with session_factory() as session:
            async with session.begin():
                return await IdempotencyRepository(session).claim_event_processing(
                    event_id="TXN-CONCURRENT-IDEMPOTENCY-001",
                    portfolio_id="PORT-CONCURRENT-IDEMPOTENCY",
                    service_name="cost-calculator",
                    correlation_id=correlation_id,
                )

    first = asyncio.create_task(claim_once("corr-concurrent-1"))
    second = asyncio.create_task(claim_once("corr-concurrent-2"))
    await workers_ready.wait()
    release_workers.set()

    claim_results = await asyncio.gather(first, second)

    assert sorted(claim_results) == [False, True]

    row_count = await async_db_session.scalar(
        select(func.count())
        .select_from(ProcessedEvent)
        .where(
            ProcessedEvent.event_id == "TXN-CONCURRENT-IDEMPOTENCY-001",
            ProcessedEvent.service_name == "cost-calculator",
        )
    )
    processed_row = (
        await async_db_session.execute(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == "TXN-CONCURRENT-IDEMPOTENCY-001",
                ProcessedEvent.service_name == "cost-calculator",
            )
        )
    ).scalar_one()

    assert row_count == 1
    assert processed_row.portfolio_id == "PORT-CONCURRENT-IDEMPOTENCY"
    assert processed_row.correlation_id in {"corr-concurrent-1", "corr-concurrent-2"}
