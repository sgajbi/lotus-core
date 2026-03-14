from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.services.financial_reconciliation_service.app.repositories import (
    reconciliation_repository as reconciliation_repo,
)

pytestmark = pytest.mark.asyncio


class _AsyncContextManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.begin_nested = MagicMock(return_value=_AsyncContextManager())
    session.refresh.return_value = None
    return session


async def test_create_run_normalizes_sentinel_correlation(mock_db_session: AsyncMock):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    repository.get_run_by_dedupe_key = AsyncMock(return_value=None)

    run, created = await repository.create_run(
        reconciliation_type="transaction_cashflow",
        portfolio_id="P1",
        business_date=date(2025, 8, 10),
        epoch=1,
        requested_by="system",
        dedupe_key="dedupe-1",
        correlation_id="<not-set>",
        tolerance=Decimal("0.01"),
    )

    assert created is True
    assert run.correlation_id is None
    mock_db_session.add.assert_called_once_with(run)
    mock_db_session.refresh.assert_awaited_once_with(run)


async def test_create_run_returns_existing_row_after_dedupe_integrity_race(
    mock_db_session: AsyncMock,
):
    repository = reconciliation_repo.ReconciliationRepository(mock_db_session)
    existing_run = MagicMock(run_id="recon-existing")
    repository.get_run_by_dedupe_key = AsyncMock(
        side_effect=[None, existing_run]
    )
    mock_db_session.flush.side_effect = IntegrityError("stmt", "params", Exception("duplicate"))

    run, created = await repository.create_run(
        reconciliation_type="transaction_cashflow",
        portfolio_id="P1",
        business_date=date(2025, 8, 10),
        epoch=1,
        requested_by="system",
        dedupe_key="dedupe-1",
        correlation_id="corr-1",
        tolerance=Decimal("0.01"),
    )

    assert run is existing_run
    assert created is False
    assert repository.get_run_by_dedupe_key.await_count == 2
