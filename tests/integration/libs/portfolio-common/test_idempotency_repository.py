import asyncio
import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import ProcessedEvent
from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
    pytest.mark.resilience,
]

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c167b2c3d52e_fix_scope_transaction_event_fences.py"
)


@pytest.fixture(scope="module", autouse=True)
def transaction_fence_tenant_schema(db_engine) -> None:
    """Apply the branch migration when the container image still reflects base main."""

    with db_engine.begin() as connection:
        if "tenant_id" in {
            column["name"] for column in inspect(connection).get_columns("processed_events")
        }:
            return
        migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
        migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))
        migration["upgrade"]()


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
                    service_name="portfolio-transaction-processing",
                    correlation_id=correlation_id,
                    tenant_id="tenant-a",
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
            ProcessedEvent.service_name == "portfolio-transaction-processing",
            ProcessedEvent.tenant_id == "tenant-a",
        )
    )
    processed_row = (
        await async_db_session.execute(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == "TXN-CONCURRENT-IDEMPOTENCY-001",
                ProcessedEvent.service_name == "portfolio-transaction-processing",
                ProcessedEvent.tenant_id == "tenant-a",
            )
        )
    ).scalar_one()

    assert row_count == 1
    assert processed_row.portfolio_id == "PORT-CONCURRENT-IDEMPOTENCY"
    assert processed_row.tenant_id == "tenant-a"
    assert processed_row.correlation_id in {"corr-concurrent-1", "corr-concurrent-2"}


async def test_same_transaction_keys_are_independent_between_tenants(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = IdempotencyRepository(async_db_session)

    tenant_a = await repository.claim_semantic_event_processing(
        event_id="SOURCE-TXN-001",
        portfolio_id="PORT-A",
        service_name="portfolio-transaction-processing",
        semantic_key="BUY|PORTFOLIO|2026-09-07|SOURCE-TXN-001",
        payload_fingerprint="fingerprint-a",
        tenant_id="tenant-a",
    )
    tenant_b = await repository.claim_semantic_event_processing(
        event_id="SOURCE-TXN-001",
        portfolio_id="PORT-B",
        service_name="portfolio-transaction-processing",
        semantic_key="BUY|PORTFOLIO|2026-09-07|SOURCE-TXN-001",
        payload_fingerprint="fingerprint-b",
        tenant_id="tenant-b",
    )
    await async_db_session.commit()

    assert tenant_a is SemanticEventClaimOutcome.CLAIMED
    assert tenant_b is SemanticEventClaimOutcome.CLAIMED
    assert await async_db_session.scalar(select(func.count()).select_from(ProcessedEvent)) == 2


async def test_same_tenant_semantic_duplicate_and_conflict_remain_deterministic(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = IdempotencyRepository(async_db_session)
    claim = {
        "portfolio_id": "PORT-A",
        "service_name": "portfolio-transaction-processing",
        "semantic_key": "BUY|PORTFOLIO|2026-09-07|SOURCE-TXN-001",
        "tenant_id": "tenant-a",
    }

    first = await repository.claim_semantic_event_processing(
        event_id="SOURCE-TXN-001",
        payload_fingerprint="fingerprint-a",
        **claim,
    )
    duplicate = await repository.claim_semantic_event_processing(
        event_id="SOURCE-TXN-002",
        payload_fingerprint="fingerprint-a",
        **claim,
    )
    conflict = await repository.claim_semantic_event_processing(
        event_id="SOURCE-TXN-003",
        payload_fingerprint="fingerprint-changed",
        **claim,
    )

    assert first is SemanticEventClaimOutcome.CLAIMED
    assert duplicate is SemanticEventClaimOutcome.SEMANTIC_DUPLICATE
    assert conflict is SemanticEventClaimOutcome.SEMANTIC_CONFLICT


async def test_rolled_back_tenant_claim_can_be_retried(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = IdempotencyRepository(async_db_session)
    claim = {
        "event_id": "SOURCE-TXN-ROLLBACK",
        "portfolio_id": "PORT-A",
        "service_name": "portfolio-transaction-processing",
        "tenant_id": "tenant-a",
    }

    assert await repository.claim_event_processing(**claim) is True
    await async_db_session.rollback()
    assert await repository.claim_event_processing(**claim) is True
    await async_db_session.commit()

    assert (
        await async_db_session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(ProcessedEvent.event_id == "SOURCE-TXN-ROLLBACK")
        )
        == 1
    )
