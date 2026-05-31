from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.simulation_repository import SimulationRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> SimulationRepository:
    return SimulationRepository(mock_db_session)


async def test_create_session_persists_and_refreshes(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    mock_db_session.refresh = AsyncMock(side_effect=lambda obj: None)

    created = await repository.create_session(portfolio_id="P1", created_by="tester", ttl_hours=12)

    assert created.portfolio_id == "P1"
    assert created.status == "ACTIVE"
    assert created.version == 1
    assert created.created_by == "tester"
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_awaited_once()
    mock_db_session.refresh.assert_awaited_once()


async def test_get_session_returns_first_scalar(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    expected = SimpleNamespace(session_id="S1")
    result_obj = MagicMock()
    result_obj.scalars.return_value.first.return_value = expected
    mock_db_session.execute = AsyncMock(return_value=result_obj)

    actual = await repository.get_session("S1")
    assert actual is expected


async def test_close_session_increments_version(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    session = SimpleNamespace(status="ACTIVE", version=2)

    closed = await repository.close_session(session)

    assert closed.status == "CLOSED"
    assert closed.version == 3
    mock_db_session.commit.assert_awaited_once()
    mock_db_session.refresh.assert_awaited_once_with(session)


async def test_add_changes_persists_rows_and_increments_session(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    session = SimpleNamespace(session_id="S1", portfolio_id="P1", version=3)
    mock_db_session.refresh = AsyncMock(side_effect=lambda obj: None)

    updated_session, rows = await repository.add_changes(
        session,
        [
            {
                "security_id": "SEC_AAPL_US",
                "transaction_type": "BUY",
                "quantity": 10,
                "price": 100.5,
                "amount": None,
                "currency": "USD",
                "metadata": {"source": "unit-test"},
            }
        ],
    )

    assert updated_session.version == 4
    assert len(rows) == 1
    assert rows[0].security_id == "SEC_AAPL_US"
    assert rows[0].quantity == Decimal("10")
    assert rows[0].price == Decimal("100.5")
    assert rows[0].amount is None
    mock_db_session.commit.assert_awaited_once()
    assert mock_db_session.refresh.await_count >= 2


async def test_add_changes_normalizes_blank_optional_amounts(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    session = SimpleNamespace(session_id="S1", portfolio_id="P1", version=3)
    mock_db_session.refresh = AsyncMock(side_effect=lambda obj: None)

    _updated_session, rows = await repository.add_changes(
        session,
        [
            {
                "security_id": "SEC_CASH_USD",
                "transaction_type": "CASH_ADJUSTMENT",
                "quantity": " ",
                "price": "",
                "amount": "12.50",
                "currency": "USD",
            }
        ],
    )

    assert rows[0].quantity is None
    assert rows[0].price is None
    assert rows[0].amount == Decimal("12.50")


async def test_delete_change_rolls_back_when_change_missing(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    session = SimpleNamespace(session_id="S1", version=1)
    execute_result = SimpleNamespace(rowcount=0)
    mock_db_session.execute = AsyncMock(return_value=execute_result)

    deleted = await repository.delete_change(session, "C404")

    assert deleted is False
    mock_db_session.rollback.assert_awaited_once()
    mock_db_session.commit.assert_not_awaited()


async def test_delete_change_increments_version_on_success(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    session = SimpleNamespace(session_id="S1", version=1)
    execute_result = SimpleNamespace(rowcount=1)
    mock_db_session.execute = AsyncMock(return_value=execute_result)

    deleted = await repository.delete_change(session, "C1")

    assert deleted is True
    assert session.version == 2
    mock_db_session.commit.assert_awaited_once()
    mock_db_session.refresh.assert_awaited_once_with(session)


async def test_get_changes_orders_and_returns_all(
    repository: SimulationRepository, mock_db_session: AsyncMock
):
    now = datetime.now(timezone.utc)
    expected_rows = [SimpleNamespace(change_id="C1", created_at=now)]
    result_obj = MagicMock()
    result_obj.scalars.return_value.all.return_value = expected_rows
    mock_db_session.execute = AsyncMock(return_value=result_obj)

    rows = await repository.get_changes("S1")
    assert rows == expected_rows
