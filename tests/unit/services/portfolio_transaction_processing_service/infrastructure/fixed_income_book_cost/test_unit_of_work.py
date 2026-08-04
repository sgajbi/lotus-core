"""Verify fixed-income authority persistence and profiles share one transaction."""

from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from services.portfolio_transaction_processing_service.app.infrastructure.fixed_income_book_cost import (  # noqa: E501
    SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork,
    SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository,
    SqlAlchemyLotAmortizedCostAuthorityRepository,
    SqlAlchemyLotAmortizedCostProfileRepository,
)


def _unit_of_work():
    session = MagicMock(spec=AsyncSession)
    session.close = AsyncMock()
    transaction = AsyncMock(spec=AsyncSessionTransaction)
    session.begin.return_value = transaction
    return (
        SqlAlchemyFixedIncomeBookCostAuthorityUnitOfWork(lambda: session),
        session,
        transaction,
    )


@pytest.mark.asyncio
async def test_builds_both_adapters_on_one_session_and_commits_once() -> None:
    unit_of_work, session, transaction = _unit_of_work()

    async with unit_of_work as entered:
        assert isinstance(entered.authority, SqlAlchemyLotAmortizedCostAuthorityRepository)
        assert isinstance(entered.profiles, SqlAlchemyLotAmortizedCostProfileRepository)
        assert isinstance(
            entered.correction_replay,
            SqlAlchemyFixedIncomeBookCostCorrectionReplayRepository,
        )
        assert entered.authority._session is session
        assert entered.profiles._session is session
        assert entered.correction_replay._session is session
        await entered.commit()

    transaction.start.assert_awaited_once_with()
    transaction.commit.assert_awaited_once_with()
    transaction.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_error", [False, True])
async def test_rolls_back_every_uncommitted_exit(raise_error: bool) -> None:
    unit_of_work, session, transaction = _unit_of_work()

    with pytest.raises(RuntimeError) if raise_error else nullcontext():
        async with unit_of_work:
            if raise_error:
                raise RuntimeError("materialization failed")

    transaction.commit.assert_not_awaited()
    transaction.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_rejects_adapter_access_before_entry_and_second_commit() -> None:
    unit_of_work, _session, transaction = _unit_of_work()

    with pytest.raises(RuntimeError, match="authority adapter is not initialized"):
        _ = unit_of_work.authority
    with pytest.raises(RuntimeError, match="profiles adapter is not initialized"):
        _ = unit_of_work.profiles
    with pytest.raises(RuntimeError, match="correction replay adapter is not initialized"):
        _ = unit_of_work.correction_replay

    async with unit_of_work:
        await unit_of_work.commit()
        with pytest.raises(RuntimeError, match="already committed"):
            await unit_of_work.commit()

    transaction.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_closes_session_when_transaction_start_fails() -> None:
    unit_of_work, session, transaction = _unit_of_work()
    transaction.start.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with unit_of_work:
            pytest.fail("unit of work should not enter")

    transaction.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()
