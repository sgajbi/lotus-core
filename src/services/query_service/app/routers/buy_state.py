from fastapi import APIRouter, Depends, HTTPException, Path, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.buy_state_dto import (
    AccruedIncomeOffsetsResponse,
    BuyCashLinkageResponse,
    PositionLotsResponse,
)
from ..services.buy_state_service import BuyStateService

router = APIRouter(prefix="/portfolios", tags=["BUY State"])

BUY_STATE_NOT_FOUND_RESPONSE_EXAMPLE = {
    "detail": "BUY state not found for portfolio PORT-STATE-001 and security SEC-US-AAPL"
}
BUY_CASH_LINKAGE_NOT_FOUND_RESPONSE_EXAMPLE = {
    "detail": (
        "BUY cash linkage not found for portfolio PORT-STATE-001 and transaction "
        "TXN-BUY-2026-0001"
    )
}


def get_buy_state_service(db: AsyncSession = Depends(get_async_db_session)) -> BuyStateService:
    return BuyStateService(db)


@router.get(
    "/{portfolio_id}/positions/{security_id}/lots",
    response_model=PositionLotsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "BUY lot state not found.",
            "content": {"application/json": {"example": BUY_STATE_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get BUY Lot State for a Position",
    description=(
        "Returns durable BUY lot records for a portfolio-security key, including linkage and "
        "policy metadata used for lifecycle traceability. Use this endpoint for transaction-state "
        "audit, reconciliation, and support investigation when a caller needs the underlying BUY "
        "lot ledger; do not use it as a general holdings or reporting read."
    ),
)
async def get_position_lots(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-STATE-001"],
    ),
    security_id: str = Path(
        ...,
        description="Security identifier for the BUY-state position key.",
        examples=["SEC-US-AAPL"],
    ),
    service: BuyStateService = Depends(get_buy_state_service),
):
    try:
        return await service.get_position_lots(portfolio_id=portfolio_id, security_id=security_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{portfolio_id}/positions/{security_id}/accrued-offsets",
    response_model=AccruedIncomeOffsetsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "BUY accrued-income offset state not found.",
            "content": {"application/json": {"example": BUY_STATE_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get BUY Accrued-Income Offset State",
    description=(
        "Returns accrued-income offset state initialized by BUY events for a "
        "portfolio-security key. Use this endpoint for fixed-income audit, income-support, and "
        "reconciliation investigation when the caller needs the persisted BUY-side offset ledger; "
        "do not use it as a portfolio-income summary route."
    ),
)
async def get_accrued_offsets(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-STATE-001"],
    ),
    security_id: str = Path(
        ...,
        description="Security identifier for the BUY-state position key.",
        examples=["SEC-US-AAPL"],
    ),
    service: BuyStateService = Depends(get_buy_state_service),
):
    try:
        return await service.get_accrued_offsets(portfolio_id=portfolio_id, security_id=security_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{portfolio_id}/transactions/{transaction_id}/cash-linkage",
    response_model=BuyCashLinkageResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "BUY cash linkage state not found.",
            "content": {
                "application/json": {"example": BUY_CASH_LINKAGE_NOT_FOUND_RESPONSE_EXAMPLE}
            },
        }
    },
    summary="Get BUY Cash Linkage State",
    description=(
        "Returns security-side BUY linkage fields and linked cashflow details for reconciliation. "
        "Use this endpoint for transaction-level audit and settlement investigation when a caller "
        "needs the persisted BUY-to-cash linkage; do not use it as a general cash-balance or "
        "portfolio-cashflow read."
    ),
)
async def get_buy_cash_linkage(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-STATE-001"],
    ),
    transaction_id: str = Path(
        ...,
        description="Security-side BUY transaction identifier.",
        examples=["TXN-BUY-2026-0001"],
    ),
    service: BuyStateService = Depends(get_buy_state_service),
):
    try:
        return await service.get_buy_cash_linkage(
            portfolio_id=portfolio_id, transaction_id=transaction_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
