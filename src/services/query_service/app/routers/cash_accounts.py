from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.cash_account_dto import CashAccountQueryResponse
from ..services.cash_account_service import CashAccountService

router = APIRouter(prefix="/portfolios", tags=["Cash Accounts"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-CASH-001 not found"}


def get_cash_account_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CashAccountService:
    return CashAccountService(db)


@router.get(
    "/{portfolio_id}/cash-accounts",
    response_model=CashAccountQueryResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get canonical cash accounts for a portfolio",
    description=(
        "Returns source-owned canonical cash-account master records for one portfolio. "
        "Use this endpoint for canonical account identity and lifecycle metadata; "
        "use reporting cash-balances when balances and translated totals are required."
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
