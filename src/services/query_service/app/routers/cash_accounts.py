from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Path, Query, status

from ..dependencies import get_cash_account_service
from ..dtos.cash_account_dto import CashAccountQueryResponse
from ..services.cash_account_service import CashAccountService
from .http_errors import value_error_to_http

router = APIRouter(prefix="/portfolios", tags=["Cash Accounts"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-CASH-001 not found"}


@router.get(
    "/{portfolio_id}/cash-accounts",
    response_model=CashAccountQueryResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get canonical cash-account master records for a portfolio",
    description=(
        "Returns source-owned canonical cash-account master records for one portfolio. "
        "Use this endpoint when a downstream consumer needs canonical account identity, "
        "currency, role, and lifecycle metadata for operator, support, or source-reference "
        "workflows. Do not use this route for per-account balances, translated cash totals, "
        "or liquidity analytics; use the strategic cash-balances route when balance publication "
        "is required."
    ),
)
async def get_cash_accounts(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-CASH-001"],
    ),
    as_of_date: date | None = Query(
        None,
        description=(
            "Optional as-of date used to filter cash-account master records by open/close window."
        ),
        examples=["2026-03-28"],
    ),
    service: CashAccountService = Depends(get_cash_account_service),
):
    try:
        return await service.get_cash_accounts(portfolio_id, as_of_date=as_of_date)
    except ValueError as exc:
        raise value_error_to_http(exc, status_code=status.HTTP_404_NOT_FOUND) from exc
