# services/query-service/app/routers/transactions.py
from datetime import date
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import pagination_params, sorting_params
from ..dtos.transaction_dto import PaginatedTransactionResponse
from ..services.transaction_service import TransactionService

router = APIRouter(prefix="/portfolios", tags=["Transactions"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-TXN-001 not found"}


@router.get(
    "/{portfolio_id}/transactions",
    response_model=PaginatedTransactionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get Transactions for a Portfolio",
    description=(
        "Returns transactions for a portfolio with filters, pagination, and sorting. "
        "Designed for transaction ledgers, audit timelines, and investigative support."
    ),
)
async def get_transactions(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-TXN-001"],
    ),
    security_id: Optional[str] = Query(
        None,
        description="Filter by a specific security ID.",
        examples=["SEC-US-IBM"],
    ),
    transaction_type: Optional[str] = Query(
        None,
        description="Filter by canonical transaction type, including FX business types.",
        examples=["FX_FORWARD"],
    ),
    component_type: Optional[str] = Query(
        None,
        description="Filter by FX component type such as FX_CONTRACT_OPEN.",
        examples=["FX_CONTRACT_OPEN"],
    ),
    linked_transaction_group_id: Optional[str] = Query(
        None,
        description="Filter by linked transaction group id for multi-row economic events.",
        examples=["LTG-FX-2026-0001"],
    ),
    fx_contract_id: Optional[str] = Query(
        None,
        description="Filter by FX contract identifier.",
        examples=["FXC-2026-0001"],
    ),
    swap_event_id: Optional[str] = Query(
        None,
        description="Filter by FX swap event identifier.",
        examples=["FXSWAP-2026-0001"],
    ),
    near_leg_group_id: Optional[str] = Query(
        None,
        description="Filter by FX swap near-leg group identifier.",
        examples=["FXSWAP-2026-0001-NEAR"],
    ),
    far_leg_group_id: Optional[str] = Query(
        None,
        description="Filter by FX swap far-leg group identifier.",
        examples=["FXSWAP-2026-0001-FAR"],
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
    as_of_date: Optional[date] = Query(
        None,
        description=(
            "Optional as-of date for booked transaction state. "
            "If omitted and include_projected is false, latest business_date is used."
        ),
        examples=["2026-03-10"],
    ),
    include_projected: bool = Query(
        False,
        description=(
            "When true, includes future-dated projected transactions "
            "beyond current business_date."
        ),
        examples=[False],
    ),
    pagination: Dict[str, int] = Depends(pagination_params),
    sorting: Dict[str, Optional[str]] = Depends(sorting_params),
    db: AsyncSession = Depends(get_async_db_session),
):
    service = TransactionService(db)
    try:
        return await service.get_transactions(
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_type=transaction_type,
            component_type=component_type,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            include_projected=include_projected,
            **pagination,
            **sorting,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
