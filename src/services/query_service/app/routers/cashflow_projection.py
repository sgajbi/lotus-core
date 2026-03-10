from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.cashflow_projection_dto import CashflowProjectionResponse
from ..services.cashflow_projection_service import CashflowProjectionService

router = APIRouter(prefix="/portfolios", tags=["Cashflow Projection"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-CF-001 not found"}


def get_cashflow_projection_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashflowProjectionService:
    return CashflowProjectionService(db)


@router.get(
    "/{portfolio_id}/cashflow-projection",
    response_model=CashflowProjectionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get Portfolio Cashflow Projection",
    description=(
        "Returns portfolio-level daily net cashflow projection for operational liquidity "
        "planning. Supports booked-only mode and projected mode for future-dated trades."
    ),
)
async def get_cashflow_projection(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-CF-001"],
    ),
    horizon_days: int = Query(
        10,
        ge=1,
        le=3650,
        description="Projection window in days from as_of_date.",
        examples=[30],
    ),
    as_of_date: Optional[date] = Query(
        None,
        description=(
            "Business-date anchor for projection baseline. "
            "If omitted, latest business_date is used."
        ),
        examples=["2026-03-10"],
    ),
    include_projected: bool = Query(
        True,
        description="When true, includes projected future-dated cashflows.",
        examples=[True],
    ),
    service: CashflowProjectionService = Depends(get_cashflow_projection_service),
):
    try:
        return await service.get_cashflow_projection(
            portfolio_id=portfolio_id,
            horizon_days=horizon_days,
            as_of_date=as_of_date,
            include_projected=include_projected,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
