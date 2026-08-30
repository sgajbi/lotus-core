# services/query-service/app/routers/transactions.py
from datetime import date
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from portfolio_common.source_data_products import source_data_product_openapi_extra

from ..application.transaction_query import TransactionRecordUnavailableError
from ..dependencies import get_transaction_service, pagination_params, sorting_params
from ..dtos.transaction_dto import (
    PaginatedTransactionResponse,
    PortfolioRealizedTaxSummaryResponse,
    TransactionRecordResponse,
)
from ..services.transaction_service import TransactionService
from .http_errors import lookup_error_to_http, value_error_to_http

router = APIRouter(prefix="/portfolios", tags=["Transactions"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-TXN-001 not found"}
INVALID_REPORTING_CURRENCY_RESPONSE_EXAMPLE = {
    "detail": "FX rate not found for USD/SGD as of 2026-03-10."
}
INVALID_REPORTING_CURRENCY_CODE_RESPONSE_EXAMPLE = {
    "detail": "Currency code must be a three-letter ISO 4217 code."
}
EXACT_TRANSACTION_SOURCE_UNAVAILABLE_RESPONSE_EXAMPLE = {
    "detail": "Transaction record source is temporarily unavailable"
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
    request: Request,
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
    service: TransactionService = Depends(get_transaction_service),
):
    try:
        return await service.get_transactions(
            tenant_context=request.state.tenant_context,
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
        raise lookup_error_to_http(exc) from exc
    except ValueError as exc:
        raise value_error_to_http(exc) from exc


@router.get(
    "/{portfolio_id}/transactions/{transaction_id}",
    response_model=TransactionRecordResponse,
    operation_id="get_portfolio_transaction_record",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid exact transaction query or reporting-currency restatement.",
            "content": {
                "application/json": {"example": INVALID_REPORTING_CURRENCY_CODE_RESPONSE_EXAMPLE}
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "No transaction with this identifier is visible within the requested portfolio."
            ),
            "content": {
                "application/json": {
                    "example": {"detail": "Transaction record not found for requested portfolio"}
                }
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": (
                "The authoritative transaction or required FX source could not be read or "
                "mapped safely."
            ),
            "content": {
                "application/json": {
                    "example": EXACT_TRANSACTION_SOURCE_UNAVAILABLE_RESPONSE_EXAMPLE
                }
            },
        },
    },
    summary="Get Exact Portfolio Transaction Record",
    description=(
        "What: Return exactly one source-owned TransactionLedgerWindow record by portfolio and "
        "transaction identity.\n"
        "How: Applies both identifiers in the authoritative Core query, loads canonical cost and "
        "latest-cashflow evidence under one repeatable-read snapshot, and returns deterministic "
        "lineage and supportability metadata. A transaction owned by another portfolio is "
        "indistinguishable from an absent transaction.\n"
        "When: Use this route for URL rehydration or record drill-down. Do not scan the paginated "
        "ledger to resolve one transaction. Optional as-of, projected-record, and "
        "reporting-currency semantics match the portfolio transaction ledger."
    ),
    openapi_extra=source_data_product_openapi_extra("TransactionLedgerWindow"),
)
async def get_transaction_record(
    request: Request,
    portfolio_id: str = Path(
        ...,
        min_length=1,
        description="Portfolio boundary that must own the transaction.",
        examples=["PORT-TXN-001"],
    ),
    transaction_id: str = Path(
        ...,
        min_length=1,
        description="Exact source-owned transaction identifier.",
        examples=["TXN-2026-0001"],
    ),
    as_of_date: Optional[date] = Query(
        None,
        description=(
            "Optional transaction/trade-date upper boundary. When omitted, it defaults to Core's "
            "latest business date unless include_projected is true; a projected exact response "
            "then reports the selected transaction's trade date. It does not represent booking "
            "or correction receipt time."
        ),
        examples=["2026-03-10"],
    ),
    include_projected: bool = Query(
        False,
        description="When true, allow an exact future-dated projected transaction record.",
        examples=[False],
    ),
    reporting_currency: Optional[str] = Query(
        None,
        description=(
            "Optional reporting currency for field-aware monetary restatement. An unbounded "
            "projected exact record selects FX evidence at the returned transaction's trade date."
        ),
        examples=["SGD"],
    ),
    service: TransactionService = Depends(get_transaction_service),
):
    try:
        return await service.get_transaction_record(
            tenant_context=request.state.tenant_context,
            portfolio_id=portfolio_id,
            transaction_id=transaction_id,
            as_of_date=as_of_date,
            include_projected=include_projected,
            reporting_currency=reporting_currency,
        )
    except LookupError as exc:
        raise lookup_error_to_http(exc) from exc
    except ValueError as exc:
        raise value_error_to_http(exc) from exc
    except TransactionRecordUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


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
    request: Request,
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
    service: TransactionService = Depends(get_transaction_service),
):
    try:
        return await service.get_realized_tax_summary(
            tenant_context=request.state.tenant_context,
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            reporting_currency=reporting_currency,
        )
    except LookupError as exc:
        raise lookup_error_to_http(exc) from exc
    except ValueError as exc:
        raise value_error_to_http(exc) from exc
