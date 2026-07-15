"""Prove the SQLAlchemy transaction boundary for position-timeseries work."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.timeseries_generator_service.app.infrastructure import (
    position_timeseries_repository_provider as provider_module,
)

pytestmark = pytest.mark.asyncio


async def test_provider_runs_operation_inside_one_database_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    transaction = AsyncMock()
    session.begin.return_value = transaction

    async def sessions():
        yield session

    monkeypatch.setattr(provider_module, "get_async_db_session", sessions)
    operation = AsyncMock(return_value="materialized")

    provider = provider_module.SqlAlchemyPositionTimeseriesRepositoryProvider()

    result = await provider.run_in_transaction(operation)

    repository = operation.await_args.args[0]
    assert result == "materialized"
    assert isinstance(repository, provider_module.TimeseriesGenerationRepository)
    assert repository.db is session
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()


async def test_provider_fails_when_database_session_source_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sessions():
        if False:
            yield MagicMock()

    monkeypatch.setattr(provider_module, "get_async_db_session", no_sessions)

    with pytest.raises(RuntimeError, match="No position-timeseries database session"):
        await provider_module.SqlAlchemyPositionTimeseriesRepositoryProvider().run_in_transaction(
            AsyncMock()
        )
