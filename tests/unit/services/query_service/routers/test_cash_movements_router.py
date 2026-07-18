from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.services.query_service.app.dependencies import get_cash_movement_service
from src.services.query_service.app.dtos.cash_movement_dto import (
    PortfolioCashMovementSummaryResponse,
)
from src.services.query_service.app.routers.cash_movements import (
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
            portfolio_currency="USD",
            buckets=[],
            cashflow_count=0,
            request_fingerprint="cash_movement_summary:" + "a" * 16,
            source_window_trust={
                "window_status": "EMPTY",
                "supportability_status": "SUPPORTED",
                "reason_codes": ["EMPTY_SOURCE_WINDOW"],
                "source_row_count": 0,
                "calculated_source_row_count": 0,
                "output_group_count": 0,
                "source_component_totals": {},
                "calculated_component_totals": {},
            },
            calculation_lineage={
                "algorithm_id": "PORTFOLIO_CASH_MOVEMENT_SUMMARY",
                "algorithm_version": 1,
                "intermediate_precision": 50,
                "input_content_hash": "a" * 64,
                "calculation_content_hash": "b" * 64,
                "output_content_hash": "c" * 64,
            },
            notes="Evidence only.",
        )
    )

    response = await get_cash_movement_summary(
        portfolio_id="P1",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        tenant_id="tenant-a",
        service=service,
    )

    assert response.portfolio_id == "P1"
    service.get_cash_movement_summary.assert_awaited_once_with(
        portfolio_id="P1",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        tenant_id="tenant-a",
    )


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
            tenant_id=None,
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
            tenant_id=None,
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert "P404" in exc_info.value.detail


def test_get_cash_movement_service_factory() -> None:
    service = get_cash_movement_service(db=MagicMock())
    assert isinstance(service, CashMovementService)
