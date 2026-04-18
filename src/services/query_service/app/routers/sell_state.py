from fastapi import APIRouter, Depends, HTTPException, Path, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.sell_state_dto import SellCashLinkageResponse, SellDisposalsResponse
from ..services.sell_state_service import SellStateService

router = APIRouter(prefix="/portfolios", tags=["SELL State"])

SELL_STATE_NOT_FOUND_RESPONSE_EXAMPLE = {
    "detail": "SELL state not found for portfolio PORT-STATE-001 and security SEC-US-AAPL"
}
SELL_CASH_LINKAGE_NOT_FOUND_RESPONSE_EXAMPLE = {
    "detail": (
        "SELL cash linkage not found for portfolio PORT-STATE-001 and transaction "
        "TXN-SELL-2026-0001"
    )
}


def get_sell_state_service(db: AsyncSession = Depends(get_async_db_session)) -> SellStateService:
    return SellStateService(db)


@router.get(
    "/{portfolio_id}/positions/{security_id}/sell-disposals",
    response_model=SellDisposalsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "SELL disposal state not found.",
            "content": {"application/json": {"example": SELL_STATE_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get SELL Disposal State for a Position",
    description=(
        "Returns SELL disposal records for a portfolio-security key, including disposed quantity, "
        "disposed cost basis, realized P&L, and policy/linkage metadata for audit and "
        "reconciliation. Use this endpoint for transaction-state audit, realized-P&L "
        "traceability, and disposal-method investigation when the caller needs persisted SELL "
        "disposal rows; do not use it as a general performance, tax-reporting, or holdings read."
    ),
)
async def get_sell_disposals(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-STATE-001"],
    ),
    security_id: str = Path(
        ...,
        description="Security identifier for the SELL-state position key.",
        examples=["SEC-US-AAPL"],
    ),
    service: SellStateService = Depends(get_sell_state_service),
):
    try:
        return await service.get_sell_disposals(portfolio_id=portfolio_id, security_id=security_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage",
    response_model=SellCashLinkageResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "SELL cash linkage state not found.",
            "content": {
                "application/json": {"example": SELL_CASH_LINKAGE_NOT_FOUND_RESPONSE_EXAMPLE}
            },
        }
    },
    summary="Get SELL Cash Linkage State",
    description=(
        "Returns security-side SELL linkage fields and linked settlement cashflow details "
        "for deterministic reconciliation. Use this endpoint for transaction-level settlement "
        "audit when a caller needs the persisted SELL-to-cash linkage; do not use it as a "
        "portfolio cashflow, liquidity, or reporting summary route."
    ),
)
async def get_sell_cash_linkage(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-STATE-001"],
    ),
    transaction_id: str = Path(
        ...,
        description="Security-side SELL transaction identifier.",
        examples=["TXN-SELL-2026-0001"],
    ),
    service: SellStateService = Depends(get_sell_state_service),
):
    try:
        return await service.get_sell_cash_linkage(
            portfolio_id=portfolio_id, transaction_id=transaction_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
