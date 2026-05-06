from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.services.query_service.app.dtos.cashflow_projection_dto import (
    CashflowProjectionPoint,
    CashflowProjectionResponse,
)
from src.services.query_service.app.routers.cashflow_projection import (
    get_cashflow_projection,
    get_cashflow_projection_service,
)
from src.services.query_service.app.services.cashflow_projection_service import (
    CashflowProjectionService,
)


@pytest.mark.asyncio
async def test_get_cashflow_projection_success() -> None:
    service = MagicMock(spec=CashflowProjectionService)
    service.get_cashflow_projection = AsyncMock(
        return_value=CashflowProjectionResponse(
            generated_at=datetime(2026, 3, 1, 1, 5, tzinfo=UTC),
            portfolio_id="P1",
            as_of_date=date(2026, 3, 1),
            range_start_date=date(2026, 3, 1),
            range_end_date=date(2026, 3, 11),
            include_projected=True,
            points=[
                CashflowProjectionPoint(
                    projection_date=date(2026, 3, 2),
                    net_cashflow=1,
                    projected_cumulative_cashflow=1,
                )
            ],
            total_net_cashflow=1,
            projection_days=10,
        )
    )

    response = await get_cashflow_projection(
        portfolio_id="P1",
        horizon_days=10,
        as_of_date=date(2026, 3, 1),
        include_projected=True,
        service=service,
    )

    assert response.portfolio_id == "P1"
    service.get_cashflow_projection.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_cashflow_projection_maps_value_error_to_404() -> None:
    service = MagicMock(spec=CashflowProjectionService)
    service.get_cashflow_projection = AsyncMock(
        side_effect=ValueError("Portfolio with id P404 not found")
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_cashflow_projection(
            portfolio_id="P404",
            horizon_days=10,
            as_of_date=date(2026, 3, 1),
            include_projected=False,
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert "P404" in exc_info.value.detail


def test_get_cashflow_projection_service_factory() -> None:
    service = get_cashflow_projection_service(db=MagicMock())
    assert isinstance(service, CashflowProjectionService)
