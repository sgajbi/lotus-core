from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
    SqlAlchemyTransactionIdempotencyAdapter,
    SqlAlchemyTransactionProcessingUnitOfWork,
)


def _unit_of_work():
    session = MagicMock(spec=AsyncSession)
    session.close = AsyncMock()
    transaction = AsyncMock(spec=AsyncSessionTransaction)
    session.begin.return_value = transaction
    unit_of_work = SqlAlchemyTransactionProcessingUnitOfWork(
        session_factory=lambda: session,
        cost_workflow=MagicMock(),
        cashflow_workflow=MagicMock(),
    )
    return unit_of_work, session, transaction


@pytest.mark.asyncio
async def test_unit_of_work_builds_every_adapter_from_one_session_and_commits_once() -> None:
    unit_of_work, session, transaction = _unit_of_work()

    async with unit_of_work as entered:
        assert entered.idempotency is unit_of_work.idempotency
        assert entered.cost is unit_of_work.cost
        assert entered.cashflow is unit_of_work.cashflow
        assert entered.position is unit_of_work.position
        await entered.commit()

    transaction.start.assert_awaited_once_with()
    transaction.commit.assert_awaited_once_with()
    transaction.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_error", [False, True])
async def test_unit_of_work_rolls_back_uncommitted_duplicate_or_failure(
    raise_error: bool,
) -> None:
    unit_of_work, session, transaction = _unit_of_work()

    with pytest.raises(RuntimeError) if raise_error else nullcontext():
        async with unit_of_work:
            if raise_error:
                raise RuntimeError("module failed")

    transaction.commit.assert_not_awaited()
    transaction.start.assert_awaited_once_with()
    transaction.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_idempotency_adapter_uses_combined_service_identity() -> None:
    repository = AsyncMock(spec=IdempotencyRepository)
    repository.claim_event_processing.return_value = True
    adapter = SqlAlchemyTransactionIdempotencyAdapter(repository)

    claimed = await adapter.claim(
        event_id="transactions.persisted-0-42",
        portfolio_id="PB-001",
        correlation_id="corr-001",
    )

    assert claimed is True
    repository.claim_event_processing.assert_awaited_once_with(
        "transactions.persisted-0-42",
        "PB-001",
        TRANSACTION_PROCESSING_SERVICE_NAME,
        "corr-001",
    )


@pytest.mark.asyncio
async def test_unit_of_work_closes_session_when_transaction_start_fails() -> None:
    unit_of_work, session, transaction = _unit_of_work()
    transaction.start.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with unit_of_work:
            pytest.fail("unit of work should not enter")

    transaction.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_when_adapter_construction_fails() -> None:
    unit_of_work, session, transaction = _unit_of_work()
    unit_of_work._build_adapters = MagicMock(side_effect=RuntimeError("adapter unavailable"))

    with pytest.raises(RuntimeError, match="adapter unavailable"):
        async with unit_of_work:
            pytest.fail("unit of work should not enter")

    transaction.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()
