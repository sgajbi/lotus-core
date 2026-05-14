# services/query-service/app/routers/transactions.py
from datetime import date
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from portfolio_common.source_data_products import source_data_product_openapi_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import pagination_params, sorting_params
from ..dtos.transaction_dto import PaginatedTransactionResponse, PortfolioRealizedTaxSummaryResponse
from ..services.transaction_service import TransactionService

router = APIRouter(prefix="/portfolios", tags=["Transactions"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-TXN-001 not found"}
INVALID_REPORTING_CURRENCY_RESPONSE_EXAMPLE = {
    "detail": "FX rate not found for USD/SGD as of 2026-03-10."
}


@router.get(
    "/{portfolio_id}/transactions",
    response_model=PaginatedTransactionResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": (
                "Invalid transaction-ledger query, including unsupported reporting-currency "
                "restatement."
            ),
            "content": {
                "application/json": {"example": INVALID_REPORTING_CURRENCY_RESPONSE_EXAMPLE}
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        },
    },
    summary="Get Portfolio Transactions",
    description=(
        "What: Return the strategic TransactionLedgerWindow operational read for one portfolio.\n"
        "How: Publishes the canonical portfolio transaction ledger with date-window filters, "
        "instrument/security drill-down, FX and linked-event filters, optional reporting-currency "
        "restatement for monetary fields, pagination, and sorting.\n"
        "When: Use this route when a downstream consumer needs governed transaction-ledger rows "
        "rather than summary aggregations. Use `security_id` for holdings drill-down, "
        "`instrument_id` for instrument-specific inspection, and FX/event filters such as "
        "`component_type`, `linked_transaction_group_id`, `fx_contract_id`, `swap_event_id`, "
        "`near_leg_group_id`, or `far_leg_group_id` when the consumer needs multi-row economic "
        "event analysis. Use `reporting_currency` when a downstream reporting surface needs "
        "ledger rows and field-aware reporting-currency monetary restatement without falling back "
        "to deprecated reporting summary routes. Results default to latest-first ordering by "
        "`transaction_date` descending unless `sort_by` and `sort_order` are provided explicitly."
    ),
    openapi_extra=source_data_product_openapi_extra("TransactionLedgerWindow"),
)
async def get_transactions(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-TXN-001"],
    ),
    instrument_id: Optional[str] = Query(
        None,
        description="Filter by a specific instrument identifier.",
        examples=["INST-AAPL-USD"],
    ),
    security_id: Optional[str] = Query(
        None,
        description=(
            "Filter by a specific security identifier for holdings drill-down and latest "
            "transaction retrieval within the portfolio."
        ),
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
    reporting_currency: Optional[str] = Query(
        None,
        description=(
            "Optional reporting currency for restated monetary fields on each returned ledger row. "
            "Use this when a downstream needs strategic transaction rows plus reporting-currency "
            "amounts for reporting or aggregation workflows."
        ),
        examples=["SGD"],
    ),
    include_projected: bool = Query(
        False,
        description=(
            "When true, includes future-dated projected transactions beyond current business_date."
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
            instrument_id=instrument_id,
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
            reporting_currency=reporting_currency,
            **pagination,
            **sorting,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/{portfolio_id}/realized-tax-summary",
    response_model=PortfolioRealizedTaxSummaryResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid realized-tax summary query.",
            "content": {
                "application/json": {"example": INVALID_REPORTING_CURRENCY_RESPONSE_EXAMPLE}
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        },
    },
    summary="Get Portfolio Realized Tax Summary",
    description=(
        "What: Return a portfolio-level summary of explicit source-recorded realized tax evidence "
        "from booked transaction ledger rows.\n"
        "How: Aggregates withholding tax and other recorded tax or interest deduction amounts by "
        "source currency, optionally restating totals into a requested reporting currency using "
        "Core FX evidence.\n"
        "When: Use this route when downstream consumers need auditable portfolio-level tax "
        "evidence without reconstructing tax totals from ledger rows. The response is source "
        "evidence only and must not be used as tax advice, after-tax optimization, tax-loss "
        "harvesting suitability, jurisdiction-specific recommendation, client-tax approval, "
        "tax-reporting certification, or OMS acknowledgement."
    ),
    openapi_extra=source_data_product_openapi_extra("PortfolioRealizedTaxSummary"),
)
async def get_realized_tax_summary(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-TXN-001"],
    ),
    start_date: Optional[date] = Query(
        None,
        description="The start date for the transaction-date window filter (inclusive).",
        examples=["2026-01-01"],
    ),
    end_date: Optional[date] = Query(
        None,
        description="The end date for the transaction-date window filter (inclusive).",
        examples=["2026-03-31"],
    ),
    as_of_date: Optional[date] = Query(
        None,
        description=(
            "Optional as-of date for booked transaction state. If omitted, latest business_date "
            "is used."
        ),
        examples=["2026-03-31"],
    ),
    reporting_currency: Optional[str] = Query(
        None,
        description=("Optional reporting currency for restating aggregated explicit tax totals."),
        examples=["SGD"],
    ),
    db: AsyncSession = Depends(get_async_db_session),
):
    service = TransactionService(db)
    try:
        return await service.get_realized_tax_summary(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            reporting_currency=reporting_currency,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
