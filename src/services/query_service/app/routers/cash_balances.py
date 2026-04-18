from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from portfolio_common.source_data_products import source_data_product_openapi_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import CashBalancesResponse
from ..services.cash_balance_service import CashBalanceService

router = APIRouter(prefix="/portfolios", tags=["Cash Balances"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-CASH-001 not found"}
BAD_REQUEST_RESPONSE_EXAMPLE = {"detail": "No business date is available for cash balance queries."}


def get_cash_balance_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashBalanceService:
    return CashBalanceService(db)


@router.get(
    "/{portfolio_id}/cash-balances",
    response_model=CashBalancesResponse,
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
    summary="Get strategic cash-account balances for a portfolio",
    description=(
        "What: Return the strategic HoldingsAsOf cash-account balance read for one portfolio.\n"
        "How: Resolves the latest booked or explicit as-of-date cash positions, preserves "
        "source-owned per-account identity, and publishes native, portfolio-currency, and "
        "reporting-currency balances with HoldingsAsOf runtime metadata.\n"
        "When: Use this route when a downstream consumer needs cash-account balances or translated "
        "cash totals without rebuilding them from broad holdings state. Prefer this contract for "
        "new gateway, advise, or report integrations. Do not use it as a substitute for canonical "
        "cash-account master "
        "metadata, broad holdings publication, or performance/risk aggregation."
    ),
    openapi_extra=source_data_product_openapi_extra("HoldingsAsOf"),
)
async def get_cash_balances(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-CASH-001"],
    ),
    as_of_date: date | None = Query(
        None,
        description=(
            "Optional as-of date for booked cash-account balances. When omitted, lotus-core "
            "resolves the latest booked business date."
        ),
        examples=["2026-03-27"],
    ),
    reporting_currency: str | None = Query(
        None,
        description=(
            "Optional reporting currency. Defaults to the portfolio currency when omitted."
        ),
        examples=["USD"],
    ),
    service: CashBalanceService = Depends(get_cash_balance_service),
):
    try:
        return await service.get_cash_balances(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            reporting_currency=reporting_currency,
        )
    except ValueError as exc:
        message = str(exc)
        if "Portfolio with id" in message and "not found" in message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
