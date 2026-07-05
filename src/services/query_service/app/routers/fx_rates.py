# services/query-service/app/routers/fx_rates.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..application.collection_window_policy import (
    CollectionWindowValidationError,
    validate_required_bounded_date_window,
)
from ..dependencies import get_fx_rate_service
from ..dtos.fx_rate_dto import FxRateResponse
from ..services.fx_rate_service import FxRateService
from .http_errors import collection_window_error_to_http

router = APIRouter(prefix="/fx-rates", tags=["FX Rates"])


@router.get(
    "/",
    response_model=FxRateResponse,
    summary="Get FX-rate series for a currency pair",
    description=(
        "Returns FX rates for a currency pair over an optional date range. "
        "Use this route for source-owned FX conversion history, valuation conversion checks, and "
        "reconciliation diagnostics. Callers must provide both `start_date` and `end_date`; the "
        "window is capped at ten years. Do not use it as a substitute for portfolio performance, "
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
        description="Required start date for the bounded FX-rate-series window (inclusive).",
        examples=["2026-01-01"],
    ),
    end_date: Optional[date] = Query(
        None,
        description="Required end date for the bounded FX-rate-series window (inclusive).",
        examples=["2026-03-31"],
    ),
    service: FxRateService = Depends(get_fx_rate_service),
):
    try:
        validate_required_bounded_date_window(
            source_product="FxRateSeries",
            start_date=start_date,
            end_date=end_date,
        )
        return await service.get_fx_rates(
            from_currency=from_currency.upper(),
            to_currency=to_currency.upper(),
            start_date=start_date,
            end_date=end_date,
        )
    except CollectionWindowValidationError as exc:
        raise collection_window_error_to_http(exc) from exc
