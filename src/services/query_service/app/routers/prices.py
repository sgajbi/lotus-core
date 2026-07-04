# services/query-service/app/routers/prices.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_market_price_service
from ..dtos.price_dto import MarketPriceResponse
from ..services.price_service import MarketPriceService

router = APIRouter(prefix="/prices", tags=["Market Prices"])


@router.get(
    "/",
    response_model=MarketPriceResponse,
    summary="Get market-price series for a security",
    description=(
        "Returns market price series for a security with optional date-range filtering. "
        "Use this route for source-owned pricing history, valuation checks, and market-data "
        "diagnostics; do not use it as a substitute for performance analytics, portfolio "
        "valuation outputs, or holdings reads."
    ),
)
async def get_prices(
    security_id: str = Query(
        ...,
        description="Security identifier for the market-price series request.",
        examples=["SEC-US-AAPL"],
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
    service: MarketPriceService = Depends(get_market_price_service),
):
    return await service.get_prices(
        security_id=security_id, start_date=start_date, end_date=end_date
    )
