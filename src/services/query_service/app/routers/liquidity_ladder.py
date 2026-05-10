from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from portfolio_common.source_data_products import source_data_product_openapi_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.liquidity_ladder_dto import PortfolioLiquidityLadderResponse
from ..services.liquidity_ladder_service import (
    DEFAULT_HORIZON_DAYS,
    MAX_HORIZON_DAYS,
    PortfolioLiquidityLadderService,
)

router = APIRouter(prefix="/portfolios", tags=["Liquidity Ladder"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-001 not found"}
BAD_REQUEST_RESPONSE_EXAMPLE = {"detail": "horizon_days must be between 0 and 366."}


def get_liquidity_ladder_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioLiquidityLadderService:
    return PortfolioLiquidityLadderService(db)


@router.get(
    "/{portfolio_id}/liquidity-ladder",
    response_model=PortfolioLiquidityLadderResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Request could not be resolved.",
            "content": {"application/json": {"example": BAD_REQUEST_RESPONSE_EXAMPLE}},
        },
    },
    summary="Get source-owned portfolio liquidity ladder evidence",
    description=(
        "What: Return the PortfolioLiquidityLadder source-data product for one private-banking "
        "portfolio.\n"
        "How: Resolves current cash balances from source holdings, groups non-cash holdings by "
        "instrument liquidity tier, and overlays booked plus optional projected settlement-dated "
        "cashflows into deterministic cash-availability buckets.\n"
        "When: Use this route when downstream consumers need source-owned liquidity evidence for "
        "portfolio monitoring, DPM supportability, or client reporting. Do not use it as an "
        "advice recommendation, OMS execution forecast, tax methodology, best-execution "
        "assessment, or predictive market-impact model."
    ),
    openapi_extra=source_data_product_openapi_extra("PortfolioLiquidityLadder"),
)
async def get_liquidity_ladder(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-001"],
    ),
    as_of_date: date | None = Query(
        None,
        description=(
            "Optional as-of date for source cash, holding, and cashflow state. When omitted, "
            "lotus-core resolves the latest booked business date."
        ),
        examples=["2026-03-27"],
    ),
    horizon_days: int = Query(
        DEFAULT_HORIZON_DAYS,
        ge=0,
        le=MAX_HORIZON_DAYS,
        description="Calendar-day liquidity horizon from the as-of date.",
        examples=[30],
    ),
    include_projected: bool = Query(
        True,
        description="Include projected settlement-dated external deposits and withdrawals.",
        examples=[True],
    ),
    service: PortfolioLiquidityLadderService = Depends(get_liquidity_ladder_service),
):
    try:
        return await service.get_liquidity_ladder(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            horizon_days=horizon_days,
            include_projected=include_projected,
        )
    except ValueError as exc:
        message = str(exc)
        if "Portfolio with id" in message and "not found" in message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
