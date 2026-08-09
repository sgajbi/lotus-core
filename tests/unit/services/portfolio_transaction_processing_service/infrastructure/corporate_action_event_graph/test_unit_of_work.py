"""Unit contracts for the corporate-action event-graph SQLAlchemy UoW."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.infrastructure.corporate_action_event_graph import (  # noqa: E501
    SqlAlchemyCorporateActionEventGraphUnitOfWork,
)

pytestmark = pytest.mark.unit


def _unit_of_work():
    session = AsyncMock()
    transaction = AsyncMock()
    session.begin = MagicMock(return_value=transaction)
    unit_of_work = SqlAlchemyCorporateActionEventGraphUnitOfWork(lambda: session)
    return unit_of_work, session, transaction


@pytest.mark.asyncio
async def test_unit_of_work_builds_repository_and_commits_once() -> None:
    unit_of_work, session, transaction = _unit_of_work()

    async with unit_of_work as entered:
        assert entered.event_graph is unit_of_work.event_graph
        await entered.commit()

    transaction.start.assert_awaited_once_with()
    transaction.commit.assert_awaited_once_with()
    transaction.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_uncommitted_work() -> None:
    unit_of_work, session, transaction = _unit_of_work()

    async with unit_of_work:
        pass

    transaction.rollback.assert_awaited_once_with()
    transaction.commit.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unit_of_work_rejects_reuse_and_double_commit() -> None:
    unit_of_work, _session, _transaction = _unit_of_work()

    async with unit_of_work:
        await unit_of_work.commit()
        with pytest.raises(RuntimeError, match="already committed"):
            await unit_of_work.commit()

    with pytest.raises(RuntimeError, match="cannot be reused"):
        await unit_of_work.__aenter__()
