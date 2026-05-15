from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from portfolio_common.source_data_products import source_data_product_openapi_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.cash_movement_dto import PortfolioCashMovementSummaryResponse
from ..services.cash_movement_service import CashMovementService

router = APIRouter(prefix="/portfolios", tags=["Cash Movements"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-CASH-001 not found"}
INVALID_DATE_WINDOW_RESPONSE_EXAMPLE = {"detail": "start_date must be on or before end_date"}


def get_cash_movement_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashMovementService:
    return CashMovementService(db)


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
        "window.\n"
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
        description="Inclusive cashflow-date window start.",
        examples=["2026-03-01"],
    ),
    end_date: date = Query(
        ...,
        description="Inclusive cashflow-date window end.",
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
        status_code = (
            status.HTTP_400_BAD_REQUEST if "start_date" in str(exc) else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=status_code, detail=str(exc))
