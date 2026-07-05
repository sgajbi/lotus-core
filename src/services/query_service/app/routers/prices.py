# services/query-service/app/routers/prices.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..application.collection_window_policy import (
    CollectionWindowValidationError,
    validate_required_bounded_date_window,
)
from ..dependencies import get_market_price_service
from ..dtos.price_dto import MarketPriceResponse
from ..services.price_service import MarketPriceService
from .http_errors import collection_window_error_to_http

router = APIRouter(prefix="/prices", tags=["Market Prices"])


@router.get(
    "/",
    response_model=MarketPriceResponse,
    summary="Get market-price series for a security",
    description=(
        "Returns market price series for a security with optional date-range filtering. "
        "Use this route for source-owned pricing history, valuation checks, and market-data "
        "diagnostics. Callers must provide both `start_date` and `end_date`; the window is capped "
        "at ten years. Do not use it as a substitute for performance analytics, portfolio "
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
        description="Required start date for the bounded price-series window (inclusive).",
        examples=["2026-01-01"],
    ),
    end_date: Optional[date] = Query(
        None,
        description="Required end date for the bounded price-series window (inclusive).",
        examples=["2026-03-31"],
    ),
    service: MarketPriceService = Depends(get_market_price_service),
):
    try:
        validate_required_bounded_date_window(
            source_product="MarketPriceSeries",
            start_date=start_date,
            end_date=end_date,
        )
        return await service.get_prices(
            security_id=security_id, start_date=start_date, end_date=end_date
        )
    except CollectionWindowValidationError as exc:
        raise collection_window_error_to_http(exc) from exc
