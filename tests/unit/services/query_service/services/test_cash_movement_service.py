from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository
from src.services.query_service.app.services.cash_movement_service import CashMovementService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=CashflowRepository)
    repo.get_portfolio_currency.return_value = "USD"
    repo.get_portfolio_cash_movement_summary.return_value = [
        (
            "CASHFLOW_IN",
            "SETTLED",
            "USD",
            False,
            True,
            2,
            Decimal("12500.00"),
            datetime(2026, 3, 5, 12, 30, tzinfo=UTC),
        ),
        (
            "TRADE_SETTLEMENT",
            "SETTLED",
            "USD",
            True,
            False,
            1,
            Decimal("-3500.00"),
            datetime(2026, 3, 6, 9, 15, tzinfo=UTC),
        ),
    ]
    return repo


async def test_cash_movement_summary_preserves_source_buckets(mock_repo: AsyncMock) -> None:
    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

    mock_repo.get_portfolio_cash_movement_summary.assert_awaited_once_with(
        portfolio_id="P1",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    assert response.product_name == "PortfolioCashMovementSummary"
    assert response.product_version == "v1"
    assert response.as_of_date == date(2026, 3, 31)
    assert response.data_quality_status == "COMPLETE"
    assert response.cashflow_count == 3
    assert response.latest_evidence_timestamp == datetime(2026, 3, 6, 9, 15, tzinfo=UTC)
    assert response.source_batch_fingerprint == "cash_movement_summary:P1:2026-03-01:2026-03-31"
    assert response.buckets[0].movement_direction == "INFLOW"
    assert response.buckets[1].movement_direction == "OUTFLOW"
    assert response.buckets[1].is_position_flow is True
    assert "not a forecast" in response.notes


async def test_cash_movement_summary_marks_empty_window_missing(mock_repo: AsyncMock) -> None:
    mock_repo.get_portfolio_cash_movement_summary.return_value = []

    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

    assert response.buckets == []
    assert response.cashflow_count == 0
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp is None


async def test_cash_movement_summary_rejects_invalid_window(mock_repo: AsyncMock) -> None:
    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="start_date must be on or before end_date"):
            await service.get_cash_movement_summary(
                portfolio_id="P1",
                start_date=date(2026, 4, 1),
                end_date=date(2026, 3, 31),
            )

    mock_repo.get_portfolio_cash_movement_summary.assert_not_awaited()


async def test_cash_movement_summary_raises_when_portfolio_missing(
    mock_repo: AsyncMock,
) -> None:
    mock_repo.get_portfolio_currency.return_value = None

    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_cash_movement_summary(
                portfolio_id="P404",
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 31),
            )
