# services/query-service/app/routers/fx_rates.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.fx_rate_dto import FxRateResponse
from ..services.fx_rate_service import FxRateService

router = APIRouter(prefix="/fx-rates", tags=["FX Rates"])


@router.get(
    "/",
    response_model=FxRateResponse,
    summary="Get FX-rate series for a currency pair",
    description=(
        "Returns FX rates for a currency pair over an optional date range. "
        "Use this route for source-owned FX conversion history, valuation conversion checks, and "
        "reconciliation diagnostics; do not use it as a substitute for portfolio performance, "
        "risk analytics, or derived reporting outputs."
    ),
)
async def get_fx_rates(
    from_currency: str = Query(
        ...,
        description="Base currency code for the requested FX series.",
        min_length=3,
        max_length=3,
        examples=["USD"],
    ),
    to_currency: str = Query(
        ...,
        description="Quote currency code for the requested FX series.",
        min_length=3,
        max_length=3,
        examples=["SGD"],
    ),
    start_date: Optional[date] = Query(
        None,
        description="The start date for the date range filter (inclusive).",
        examples=["2026-01-01"],
    ),
    end_date: Optional[date] = Query(
        None,
        description="The end date for the date range filter (inclusive).",
        examples=["2026-03-31"],
    ),
    db: AsyncSession = Depends(get_async_db_session),
):
    service = FxRateService(db)
    return await service.get_fx_rates(
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        start_date=start_date,
        end_date=end_date,
    )
