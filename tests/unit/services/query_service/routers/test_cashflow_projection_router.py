from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
)

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


def _trust_fields() -> dict[str, object]:
    return {
        "request_fingerprint": "cashflow_projection:" + "a" * 16,
        "source_window_trust": {
            "window_status": "POPULATED",
            "supportability_status": "SUPPORTED",
            "reason_codes": [],
            "source_row_count": 1,
            "calculated_source_row_count": 1,
            "output_group_count": 1,
            "source_component_totals": {"BOOKED": 1, "PROJECTED": 0},
            "calculated_component_totals": {"BOOKED": 1, "PROJECTED": 0},
        },
        "calculation_lineage": {
            "algorithm_id": "PORTFOLIO_CASHFLOW_PROJECTION",
            "algorithm_version": 1,
            "intermediate_precision": 50,
            "input_content_hash": "a" * 64,
            "calculation_content_hash": "b" * 64,
            "output_content_hash": "c" * 64,
        },
    }


@pytest.mark.asyncio
async def test_get_cashflow_projection_success() -> None:
    service = MagicMock(spec=CashflowProjectionService)
    service.get_cashflow_projection = AsyncMock(
        return_value=CashflowProjectionResponse(
            portfolio_id="P1",
            range_start_date=date(2026, 3, 1),
            range_end_date=date(2026, 3, 11),
            include_projected=True,
            portfolio_currency="USD",
            points=[
                CashflowProjectionPoint(
                    projection_date=date(2026, 3, 2),
                    booked_net_cashflow=1,
                    projected_settlement_cashflow=0,
                    net_cashflow=1,
                    projected_cumulative_cashflow=1,
                )
            ],
            total_net_cashflow=1,
            booked_total_net_cashflow=1,
            projected_settlement_total_cashflow=0,
            projection_days=10,
            **_trust_fields(),
            **source_data_product_runtime_metadata(
                as_of_date=date(2026, 3, 1),
                generated_at=datetime(2026, 3, 1, 1, 5, tzinfo=UTC),
                data_quality_status="COMPLETE",
                latest_evidence_timestamp=datetime(2026, 3, 1, 1, 4, tzinfo=UTC),
            ),
        )
    )

    response = await get_cashflow_projection(
        portfolio_id="P1",
        horizon_days=10,
        as_of_date=date(2026, 3, 1),
        include_projected=True,
        tenant_id="tenant-a",
        service=service,
    )

    assert response.portfolio_id == "P1"
    service.get_cashflow_projection.assert_awaited_once_with(
        portfolio_id="P1",
        horizon_days=10,
        as_of_date=date(2026, 3, 1),
        include_projected=True,
        tenant_id="tenant-a",
    )


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
            tenant_id=None,
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert "P404" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_cashflow_projection_maps_resolution_error_to_400() -> None:
    service = MagicMock(spec=CashflowProjectionService)
    service.get_cashflow_projection = AsyncMock(
        side_effect=ValueError("horizon_days must be between 1 and 366.")
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=367,
            as_of_date=date(2026, 3, 1),
            include_projected=False,
            tenant_id=None,
            service=service,
        )

    assert exc_info.value.status_code == 400
    assert "horizon_days" in exc_info.value.detail


def test_get_cashflow_projection_service_factory() -> None:
    service = get_cashflow_projection_service(db=MagicMock())
    assert isinstance(service, CashflowProjectionService)
