from datetime import date

from fastapi import APIRouter, Depends, Path, Query, status
from portfolio_common.source_data_products import source_data_product_openapi_extra

from ..dependencies import get_cash_movement_service
from ..dtos.cash_movement_dto import PortfolioCashMovementSummaryResponse
from ..services.cash_movement_service import MAX_CASH_MOVEMENT_WINDOW_DAYS, CashMovementService
from .http_errors import raise_value_error_as_resolution_http

router = APIRouter(prefix="/portfolios", tags=["Cash Movements"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-CASH-001 not found"}
INVALID_DATE_WINDOW_RESPONSE_EXAMPLE = {
    "detail": (
        f"cash movement summary date window must be {MAX_CASH_MOVEMENT_WINDOW_DAYS} days or less"
    )
}


@router.get(
    "/{portfolio_id}/cash-movement-summary",
    response_model=PortfolioCashMovementSummaryResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid cash movement summary date window.",
            "content": {"application/json": {"example": INVALID_DATE_WINDOW_RESPONSE_EXAMPLE}},
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        },
    },
    summary="Get Portfolio Cash Movement Summary",
    description=(
        "What: Return source-owned portfolio cash movement totals for a bounded cashflow-date "
        f"window of up to {MAX_CASH_MOVEMENT_WINDOW_DAYS} days.\n"
        "How: Aggregates latest cashflow rows by source-owned classification, timing, currency, "
        "and portfolio/position flow scope while preserving source-data product metadata.\n"
        "When: Use this route when downstream outcome, reporting, or DPM consumers need cash "
        "movement evidence without recalculating cashflow rows. Do not use it as a cashflow "
        "forecast, funding recommendation, treasury instruction, or OMS acknowledgement."
    ),
    openapi_extra=source_data_product_openapi_extra("PortfolioCashMovementSummary"),
)
async def get_cash_movement_summary(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-CASH-001"],
    ),
    start_date: date = Query(
        ...,
        description=(
            "Inclusive cashflow-date window start. The inclusive window cannot exceed "
            f"{MAX_CASH_MOVEMENT_WINDOW_DAYS} days."
        ),
        examples=["2026-03-01"],
    ),
    end_date: date = Query(
        ...,
        description=(
            "Inclusive cashflow-date window end. The inclusive window cannot exceed "
            f"{MAX_CASH_MOVEMENT_WINDOW_DAYS} days."
        ),
        examples=["2026-03-31"],
    ),
    service: CashMovementService = Depends(get_cash_movement_service),
):
    try:
        return await service.get_cash_movement_summary(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise_value_error_as_resolution_http(exc)
