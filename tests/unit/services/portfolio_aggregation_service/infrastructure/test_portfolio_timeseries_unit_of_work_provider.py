"""Prove the SQLAlchemy unit of work for portfolio-timeseries materialization."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_aggregation_service.app.infrastructure import (
    portfolio_timeseries_unit_of_work_provider as provider_module,
)

pytestmark = pytest.mark.asyncio


async def test_provider_composes_repository_and_outbox_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    transaction = AsyncMock()
    session.begin.return_value = transaction

    async def sessions():
        yield session

    monkeypatch.setattr(provider_module, "get_async_db_session", sessions)
    operation = AsyncMock(return_value="complete")
    provider = provider_module.SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider()

    result = await provider.run_in_transaction(operation)

    repository, event_stager = operation.await_args.args
    assert result == "complete"
    assert isinstance(repository, provider_module.PortfolioAggregationRepository)
    assert repository.db is session
    assert isinstance(
        event_stager,
        provider_module.TransactionalAggregationCompletionEventStager,
    )
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()


async def test_provider_fails_when_database_session_source_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sessions():
        if False:
            yield MagicMock()

    monkeypatch.setattr(provider_module, "get_async_db_session", no_sessions)

    with pytest.raises(RuntimeError, match="No portfolio-timeseries database session"):
        await provider_module.SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider().run_in_transaction(
            AsyncMock()
        )
