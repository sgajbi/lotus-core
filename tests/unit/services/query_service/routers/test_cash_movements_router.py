from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.services.query_service.app.dtos.cash_movement_dto import (
    PortfolioCashMovementSummaryResponse,
)
from src.services.query_service.app.routers.cash_movements import (
    get_cash_movement_service,
    get_cash_movement_summary,
)
from src.services.query_service.app.services.cash_movement_service import CashMovementService


@pytest.mark.asyncio
async def test_get_cash_movement_summary_success() -> None:
    service = MagicMock(spec=CashMovementService)
    service.get_cash_movement_summary = AsyncMock(
        return_value=PortfolioCashMovementSummaryResponse(
            generated_at=datetime(2026, 3, 31, 1, 5, tzinfo=UTC),
            portfolio_id="P1",
            as_of_date=date(2026, 3, 31),
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            buckets=[],
            cashflow_count=0,
            notes="Evidence only.",
        )
    )

    response = await get_cash_movement_summary(
        portfolio_id="P1",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        service=service,
    )

    assert response.portfolio_id == "P1"
    service.get_cash_movement_summary.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_cash_movement_summary_maps_excessive_window_to_400() -> None:
    service = MagicMock(spec=CashMovementService)
    service.get_cash_movement_summary = AsyncMock(
        side_effect=ValueError("cash movement summary date window must be 366 days or less")
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 1, 1),
            end_date=date(2027, 1, 2),
            service=service,
        )

    assert exc_info.value.status_code == 400
    assert "date window" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_cash_movement_summary_maps_missing_portfolio_to_404() -> None:
    service = MagicMock(spec=CashMovementService)
    service.get_cash_movement_summary = AsyncMock(
        side_effect=ValueError("Portfolio with id P404 not found")
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_cash_movement_summary(
            portfolio_id="P404",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert "P404" in exc_info.value.detail


def test_get_cash_movement_service_factory() -> None:
    service = get_cash_movement_service(db=MagicMock())
    assert isinstance(service, CashMovementService)
