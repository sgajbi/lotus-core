from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository
from src.services.query_service.app.services.cashflow_projection_service import (
    CashflowProjectionService,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=CashflowRepository)
    repo.portfolio_exists.return_value = True
    repo.get_latest_business_date.return_value = date(2026, 3, 1)

    async def _series(
        portfolio_id: str, start_date: date, end_date: date
    ) -> list[tuple[date, Decimal]]:
        universe = {
            date(2026, 3, 1): Decimal("-1000"),
            date(2026, 3, 3): Decimal("250"),
        }
        return [(d, amount) for d, amount in universe.items() if start_date <= d <= end_date]

    repo.get_portfolio_cashflow_series.side_effect = _series
    repo.get_projected_settlement_cashflow_series.return_value = []
    return repo


async def test_projection_defaults_to_latest_business_date(mock_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(portfolio_id="P1", horizon_days=10)

        mock_repo.get_portfolio_cashflow_series.assert_awaited_once_with(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 11),
        )
        mock_repo.get_projected_settlement_cashflow_series.assert_awaited_once_with(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 11),
        )
        assert response.total_net_cashflow == Decimal("-750")
        assert response.points[0].projected_cumulative_cashflow == Decimal("-1000")
        assert response.points[1].net_cashflow == Decimal("0")
        assert response.points[1].projected_cumulative_cashflow == Decimal("-1000")
        assert response.points[2].projected_cumulative_cashflow == Decimal("-750")
        assert len(response.points) == 11


async def test_projection_booked_only_caps_to_as_of_date(mock_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=10,
            as_of_date=date(2026, 3, 2),
            include_projected=False,
        )

        mock_repo.get_portfolio_cashflow_series.assert_awaited_once_with(
            portfolio_id="P1",
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
        )
        mock_repo.get_projected_settlement_cashflow_series.assert_not_awaited()
        assert response.include_projected is False
        assert response.range_end_date == date(2026, 3, 2)
        assert len(response.points) == 1
        assert response.points[0].projection_date == date(2026, 3, 2)
        assert response.points[0].net_cashflow == Decimal("0")
        assert response.notes == "Booked-only view capped at as_of_date."


async def test_projection_raises_when_portfolio_missing(mock_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        mock_repo.portfolio_exists.return_value = False
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_cashflow_projection(portfolio_id="P404")


async def test_projection_includes_future_settlement_dated_external_flows(mock_repo: AsyncMock):
    mock_repo.get_projected_settlement_cashflow_series.return_value = [
        (date(2026, 3, 4), Decimal("-18000"))
    ]

    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=4,
            as_of_date=date(2026, 3, 1),
            include_projected=True,
        )

        points = {point.projection_date: point for point in response.points}
        assert points[date(2026, 3, 4)].net_cashflow == Decimal("-18000")
        assert points[date(2026, 3, 4)].projected_cumulative_cashflow == Decimal("-18750")
        assert response.total_net_cashflow == Decimal("-18750")
        assert (
            response.notes
            == "Projected window includes settlement-dated future external cash movements."
        )
