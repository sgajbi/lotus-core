from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from ..dtos.reference_integration_dto import (
    SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES,
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
    PerformanceComponentEconomicsRow,
    PerformanceComponentEconomicsSupportability,
    PerformanceComponentEconomicsTotal,
)
from ..repositories.identifier_normalization import normalize_security_id
from .decimal_amounts import decimal_or_zero
from .reference_data_helpers import latest_reference_evidence_timestamp
from .request_fingerprint import request_fingerprint as build_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date
from .transaction_cost_curve import transaction_fee_amount

SOURCE_CONTRACT_VERSION = "performance_component_economics_v1"


async def resolve_performance_component_economics_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
) -> PerformanceComponentEconomicsResponse:
    if not await repository.portfolio_exists(portfolio_id):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")

    transactions = await repository.list_performance_component_economics_evidence(
        portfolio_id=portfolio_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
        as_of_date=request.as_of_date,
        security_ids=request.security_ids,
        transaction_types=request.transaction_types,
    )
    rows = build_performance_component_economics_rows(transactions)
    return build_performance_component_economics_response(
        portfolio_id=portfolio_id,
        request=request,
        rows=rows,
        transactions=transactions,
    )


def build_performance_component_economics_rows(
    transactions: list[Any],
) -> list[PerformanceComponentEconomicsRow]:
    return [_performance_component_economics_row(transaction) for transaction in transactions]


def build_performance_component_economics_response(
    *,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
    rows: list[PerformanceComponentEconomicsRow],
    transactions: list[Any],
) -> PerformanceComponentEconomicsResponse:
    observed_component_families = _observed_component_families(rows)
    state = "READY" if rows else "UNAVAILABLE"
    reason = (
        "PERFORMANCE_COMPONENT_ECONOMICS_READY"
        if rows
        else "PERFORMANCE_COMPONENT_ECONOMICS_EVIDENCE_NOT_FOUND"
    )
    request_scope_fingerprint = _request_scope_fingerprint(
        portfolio_id=portfolio_id,
        request=request,
    )

    return PerformanceComponentEconomicsResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        window=request.window,
        request_fingerprint=request_scope_fingerprint,
        rows=rows,
        component_totals=build_performance_component_economics_totals(rows),
        supportability=PerformanceComponentEconomicsSupportability(
            state=state,
            reason=reason,
            source_row_count=len(rows),
            observed_component_families=observed_component_families,
            missing_component_families=[
                family
                for family in SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES
                if family not in observed_component_families
            ],
        ),
        lineage={
            "source_system": "transactions",
            "source_table": "transactions,cashflows,transaction_costs",
            "contract_version": SOURCE_CONTRACT_VERSION,
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status="COMPLETE" if rows else "UNKNOWN",
            latest_evidence_timestamp=latest_reference_evidence_timestamp(transactions),
        ),
    )


def build_performance_component_economics_totals(
    rows: list[PerformanceComponentEconomicsRow],
) -> list[PerformanceComponentEconomicsTotal]:
    grouped: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for row in rows:
        _append_total(grouped, "fee", row.currency, row.trade_fee_amount)
        _append_total(grouped, "income", row.currency, row.net_interest_amount)
        _append_total(grouped, "tax", row.currency, row.withholding_tax_amount)
        _append_total(grouped, "tax", row.currency, row.other_interest_deductions_amount)
        _append_total(grouped, "realized_capital_pnl", row.currency, row.realized_capital_pnl_base)
        _append_total(grouped, "realized_fx_pnl", row.currency, row.realized_fx_pnl_base)
        _append_total(grouped, "realized_total_pnl", row.currency, row.realized_total_pnl_base)
        if row.cashflow_amount is not None and row.cashflow_currency:
            _append_total(grouped, "cashflow", row.cashflow_currency, row.cashflow_amount)

    return [
        PerformanceComponentEconomicsTotal(
            component_family=component_family,
            currency=currency,
            amount=sum(amounts, Decimal("0")),
            evidence_count=len(amounts),
        )
        for (component_family, currency), amounts in sorted(grouped.items())
    ]


def _performance_component_economics_row(transaction: Any) -> PerformanceComponentEconomicsRow:
    cashflow = getattr(transaction, "cashflow", None)
    return PerformanceComponentEconomicsRow(
        transaction_id=str(transaction.transaction_id),
        portfolio_id=str(transaction.portfolio_id),
        security_id=normalize_security_id(transaction.security_id),
        transaction_type=str(transaction.transaction_type).strip().upper(),
        transaction_date=transaction.transaction_date.date(),
        currency=str(transaction.currency).strip().upper(),
        gross_transaction_amount=decimal_or_zero(transaction.gross_transaction_amount),
        trade_fee_amount=transaction_fee_amount(transaction),
        cashflow_amount=(
            decimal_or_zero(getattr(cashflow, "amount", None)) if cashflow is not None else None
        ),
        cashflow_currency=(
            str(getattr(cashflow, "currency")).strip().upper() if cashflow is not None else None
        ),
        cashflow_classification=(
            str(getattr(cashflow, "classification")).strip().lower()
            if cashflow is not None
            else None
        ),
        cashflow_timing=(
            str(getattr(cashflow, "timing")).strip().lower() if cashflow is not None else None
        ),
        is_position_flow=(
            bool(getattr(cashflow, "is_position_flow")) if cashflow is not None else None
        ),
        is_portfolio_flow=(
            bool(getattr(cashflow, "is_portfolio_flow")) if cashflow is not None else None
        ),
        withholding_tax_amount=decimal_or_zero(
            getattr(transaction, "withholding_tax_amount", None)
        ),
        other_interest_deductions_amount=decimal_or_zero(
            getattr(transaction, "other_interest_deductions_amount", None)
        ),
        net_interest_amount=decimal_or_zero(getattr(transaction, "net_interest_amount", None)),
        realized_capital_pnl_local=decimal_or_zero(
            getattr(transaction, "realized_capital_pnl_local", None)
        ),
        realized_fx_pnl_local=decimal_or_zero(getattr(transaction, "realized_fx_pnl_local", None)),
        realized_total_pnl_local=decimal_or_zero(
            getattr(transaction, "realized_total_pnl_local", None)
        ),
        realized_capital_pnl_base=decimal_or_zero(
            getattr(transaction, "realized_capital_pnl_base", None)
        ),
        realized_fx_pnl_base=decimal_or_zero(getattr(transaction, "realized_fx_pnl_base", None)),
        realized_total_pnl_base=decimal_or_zero(
            getattr(transaction, "realized_total_pnl_base", None)
        ),
        transaction_fx_rate=getattr(transaction, "transaction_fx_rate", None),
        fx_contract_id=getattr(transaction, "fx_contract_id", None),
        source_lineage={
            "source_system": "transactions",
            "source_table": "transactions,cashflows,transaction_costs",
            "contract_version": SOURCE_CONTRACT_VERSION,
        },
    )


def _append_total(
    grouped: dict[tuple[str, str], list[Decimal]],
    component_family: str,
    currency: str,
    amount: Decimal,
) -> None:
    if amount != 0:
        grouped[(component_family, currency)].append(amount)


def _observed_component_families(rows: list[PerformanceComponentEconomicsRow]) -> list[str]:
    observed: set[str] = set()
    for row in rows:
        if row.cashflow_amount not in (None, Decimal("0")):
            observed.add("cashflow")
        if row.trade_fee_amount != 0:
            observed.add("fee")
        if row.net_interest_amount != 0:
            observed.add("income")
        if row.withholding_tax_amount != 0 or row.other_interest_deductions_amount != 0:
            observed.add("tax")
        if row.realized_capital_pnl_local != 0 or row.realized_capital_pnl_base != 0:
            observed.add("realized_capital_pnl")
        if row.realized_fx_pnl_local != 0 or row.realized_fx_pnl_base != 0:
            observed.add("realized_fx_pnl")
        if row.realized_total_pnl_local != 0 or row.realized_total_pnl_base != 0:
            observed.add("realized_total_pnl")
        if row.transaction_fx_rate is not None or row.fx_contract_id:
            observed.add("fx_context")
    return [
        family
        for family in SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES
        if family in observed
    ]


def _request_scope_fingerprint(
    *,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
) -> str:
    return build_request_fingerprint(
        {
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date.isoformat(),
            "window": {
                "start_date": request.window.start_date.isoformat(),
                "end_date": request.window.end_date.isoformat(),
            },
            "security_ids": sorted(request.security_ids or []),
            "transaction_types": sorted(request.transaction_types or []),
            "tenant_id": request.tenant_id,
        }
    )
