from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from ..dtos.reference_integration_dto import (
    SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES,
    PerformanceComponentEconomicsFeeComponent,
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
    PerformanceComponentEconomicsRow,
    PerformanceComponentEconomicsSupportability,
    PerformanceComponentEconomicsTotal,
    ReferencePageMetadata,
)
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from .decimal_amounts import decimal_or_zero
from .reference_data_helpers import latest_reference_evidence_timestamp
from .request_fingerprint import request_fingerprint as build_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date
from .transaction_cost_curve import transaction_fee_amount, unique_transaction_cost_components

SOURCE_CONTRACT_VERSION = "performance_component_economics_v1"
_ComponentPredicate = Callable[[PerformanceComponentEconomicsRow], bool]
_PerformanceEconomicsCursor = tuple[str, str, str] | tuple[()]


@dataclass(frozen=True)
class PerformanceComponentEconomicsPageScope:
    request_fingerprint: str
    after_key: _PerformanceEconomicsCursor


def performance_component_economics_page_scope(
    *,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
    cursor: dict[str, Any],
) -> PerformanceComponentEconomicsPageScope:
    request_fingerprint = _request_scope_fingerprint(portfolio_id=portfolio_id, request=request)
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != request_fingerprint:
        raise ValueError("Performance component economics page token does not match request scope.")
    last_row_key = tuple(cursor.get("last_row_key") or ())
    if len(last_row_key) not in (0, 3):
        raise ValueError("Performance component economics page token has an invalid row key.")
    return PerformanceComponentEconomicsPageScope(
        request_fingerprint=request_fingerprint,
        after_key=last_row_key,
    )


def performance_component_economics_next_page_token_payload(
    *,
    page_scope: PerformanceComponentEconomicsPageScope,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
) -> dict[str, Any] | None:
    if not has_more or not rows:
        return None
    last_row = rows[-1]
    return {
        "scope_fingerprint": page_scope.request_fingerprint,
        "last_row_key": [
            last_row.security_id,
            last_row.transaction_date.isoformat(),
            last_row.transaction_id,
        ],
    }


def performance_component_economics_page_token(
    *,
    page_scope: PerformanceComponentEconomicsPageScope,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
    encode_page_token: Callable[[dict[str, Any]], str],
) -> str | None:
    payload = performance_component_economics_next_page_token_payload(
        page_scope=page_scope,
        rows=rows,
        has_more=has_more,
    )
    if payload is None:
        return None
    return encode_page_token(payload)


async def resolve_performance_component_economics_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: PerformanceComponentEconomicsRequest,
    decode_page_token: Callable[[str | None], dict[str, Any]],
    encode_page_token: Callable[[dict[str, Any]], str],
) -> PerformanceComponentEconomicsResponse:
    if not await repository.portfolio_exists(portfolio_id):
        raise LookupError(f"Portfolio with id {portfolio_id} not found")

    portfolio_base_currency = await repository.get_portfolio_base_currency(portfolio_id)
    if portfolio_base_currency is None:
        raise LookupError(f"Portfolio with id {portfolio_id} not found")
    normalized_portfolio_base_currency = normalize_currency_code(portfolio_base_currency)
    page_scope = performance_component_economics_page_scope(
        portfolio_id=portfolio_id,
        request=request,
        cursor=decode_page_token(request.page.page_token),
    )
    transactions = await repository.list_performance_component_economics_evidence(
        portfolio_id=portfolio_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
        as_of_date=request.as_of_date,
        security_ids=request.security_ids,
        transaction_types=request.transaction_types,
        after_key=page_scope.after_key,
        limit=request.page.page_size + 1,
    )
    has_more = len(transactions) > request.page.page_size
    page_transactions = transactions[: request.page.page_size]
    rows = build_performance_component_economics_rows(page_transactions)
    next_page_token = performance_component_economics_page_token(
        page_scope=page_scope,
        rows=rows,
        has_more=has_more,
        encode_page_token=encode_page_token,
    )
    return build_performance_component_economics_response(
        portfolio_id=portfolio_id,
        request=request,
        rows=rows,
        transactions=page_transactions,
        portfolio_base_currency=normalized_portfolio_base_currency,
        request_scope_fingerprint=page_scope.request_fingerprint,
        has_more=has_more,
        next_page_token=next_page_token,
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
    portfolio_base_currency: str,
    request_scope_fingerprint: str | None = None,
    has_more: bool = False,
    next_page_token: str | None = None,
) -> PerformanceComponentEconomicsResponse:
    observed_component_families = _observed_component_families(rows)
    state = _performance_component_economics_supportability_state(rows=rows, has_more=has_more)
    reason = _performance_component_economics_supportability_reason(
        rows=rows,
        has_more=has_more,
    )
    fingerprint = request_scope_fingerprint or _request_scope_fingerprint(
        portfolio_id=portfolio_id, request=request
    )

    return PerformanceComponentEconomicsResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        window=request.window,
        request_fingerprint=fingerprint,
        rows=rows,
        component_totals=build_performance_component_economics_totals(
            rows,
            portfolio_base_currency=portfolio_base_currency,
        ),
        page=ReferencePageMetadata(
            page_size=request.page.page_size,
            sort_key="security_id:asc,transaction_date:asc,transaction_id:asc",
            returned_component_count=len(rows),
            request_scope_fingerprint=fingerprint,
            next_page_token=next_page_token,
        ),
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
            tenant_id=request.tenant_id,
            data_quality_status="PARTIAL" if has_more else ("COMPLETE" if rows else "UNKNOWN"),
            latest_evidence_timestamp=_latest_performance_evidence_timestamp(transactions),
        ),
    )


def _performance_component_economics_supportability_state(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
) -> str:
    if not rows:
        return "UNAVAILABLE"
    if has_more:
        return "DEGRADED"
    return "READY"


def _performance_component_economics_supportability_reason(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
) -> str:
    if not rows:
        return "PERFORMANCE_COMPONENT_ECONOMICS_EVIDENCE_NOT_FOUND"
    if has_more:
        return "PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL"
    return "PERFORMANCE_COMPONENT_ECONOMICS_READY"


def build_performance_component_economics_totals(
    rows: list[PerformanceComponentEconomicsRow],
    *,
    portfolio_base_currency: str,
) -> list[PerformanceComponentEconomicsTotal]:
    grouped: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for row in rows:
        for fee_component in row.trade_fee_components:
            _append_total(grouped, "fee", fee_component.currency, fee_component.amount)
        _append_total(grouped, "income", row.currency, row.net_interest_amount)
        _append_total(grouped, "tax", row.currency, row.withholding_tax_amount)
        _append_total(grouped, "tax", row.currency, row.other_interest_deductions_amount)
        _append_total(
            grouped,
            "realized_capital_pnl",
            portfolio_base_currency,
            row.realized_capital_pnl_base,
        )
        _append_total(grouped, "realized_fx_pnl", portfolio_base_currency, row.realized_fx_pnl_base)
        _append_total(
            grouped,
            "realized_total_pnl",
            portfolio_base_currency,
            row.realized_total_pnl_base,
        )
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
    trade_fee_components = _transaction_fee_components(transaction)
    trade_fee_currency = _transaction_fee_currency(trade_fee_components)
    return PerformanceComponentEconomicsRow(
        transaction_id=str(transaction.transaction_id),
        portfolio_id=str(transaction.portfolio_id),
        security_id=normalize_security_id(transaction.security_id),
        transaction_type=str(transaction.transaction_type).strip().upper(),
        transaction_date=transaction.transaction_date.date(),
        currency=str(transaction.currency).strip().upper(),
        trade_currency=_transaction_trade_currency(transaction),
        gross_transaction_amount=decimal_or_zero(transaction.gross_transaction_amount),
        trade_fee_amount=(
            trade_fee_components[0].amount if len(trade_fee_components) == 1 else Decimal("0")
        ),
        trade_fee_currency=trade_fee_currency,
        trade_fee_components=trade_fee_components,
        cashflow_amount=(
            decimal_or_zero(getattr(cashflow, "amount", None)) if cashflow is not None else None
        ),
        cashflow_currency=(
            str(getattr(cashflow, "currency")).strip().upper() if cashflow is not None else None
        ),
        cashflow_classification=(
            str(getattr(cashflow, "classification")).strip().upper()
            if cashflow is not None
            else None
        ),
        cashflow_timing=(
            str(getattr(cashflow, "timing")).strip().upper() if cashflow is not None else None
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
        realized_pnl_local_currency=_transaction_trade_currency(transaction),
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


def _latest_performance_evidence_timestamp(transactions: list[Any]):
    evidence_rows: list[Any] = []
    for transaction in transactions:
        evidence_rows.append(transaction)
        cashflow = getattr(transaction, "cashflow", None)
        if cashflow is not None:
            evidence_rows.append(cashflow)
        evidence_rows.extend(getattr(transaction, "costs", None) or [])
    return latest_reference_evidence_timestamp(evidence_rows)


def _transaction_fee_components(
    transaction: Any,
) -> list[PerformanceComponentEconomicsFeeComponent]:
    costs = [
        cost
        for cost in unique_transaction_cost_components(transaction)
        if decimal_or_zero(getattr(cost, "amount", None)) > 0
    ]
    if costs:
        grouped: dict[str, list[Decimal]] = defaultdict(list)
        for cost in costs:
            grouped[
                normalize_currency_code(
                    getattr(cost, "currency", None) or _transaction_trade_currency(transaction)
                )
            ].append(decimal_or_zero(getattr(cost, "amount", None)))
        return [
            PerformanceComponentEconomicsFeeComponent(
                currency=currency,
                amount=sum(amounts, Decimal("0")),
                evidence_count=len(amounts),
            )
            for currency, amounts in sorted(grouped.items())
        ]

    trade_fee = transaction_fee_amount(transaction)
    if trade_fee <= 0:
        return []
    return [
        PerformanceComponentEconomicsFeeComponent(
            currency=_transaction_trade_currency(transaction),
            amount=trade_fee,
            evidence_count=1,
        )
    ]


def _transaction_fee_currency(
    fee_components: list[PerformanceComponentEconomicsFeeComponent],
) -> str:
    if len(fee_components) > 1:
        return "MIXED"
    if len(fee_components) == 1:
        return fee_components[0].currency
    return ""


def _transaction_trade_currency(transaction: Any) -> str:
    trade_currency = getattr(transaction, "trade_currency", None)
    if trade_currency:
        return normalize_currency_code(trade_currency)
    return normalize_currency_code(getattr(transaction, "currency"))


def _observed_component_families(rows: list[PerformanceComponentEconomicsRow]) -> list[str]:
    observed: set[str] = set()
    for row in rows:
        observed.update(_observed_row_component_families(row))
    return [
        family
        for family in SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES
        if family in observed
    ]


def _observed_row_component_families(row: PerformanceComponentEconomicsRow) -> set[str]:
    return {family for family, predicate in _COMPONENT_FAMILY_PREDICATES if predicate(row)}


def _has_cashflow_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.cashflow_amount not in (None, Decimal("0"))


def _has_fee_component(row: PerformanceComponentEconomicsRow) -> bool:
    return bool(row.trade_fee_components) or row.trade_fee_amount != 0


def _has_income_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.net_interest_amount != 0


def _has_tax_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.withholding_tax_amount != 0 or row.other_interest_deductions_amount != 0


def _has_realized_capital_pnl_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.realized_capital_pnl_local != 0 or row.realized_capital_pnl_base != 0


def _has_realized_fx_pnl_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.realized_fx_pnl_local != 0 or row.realized_fx_pnl_base != 0


def _has_realized_total_pnl_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.realized_total_pnl_local != 0 or row.realized_total_pnl_base != 0


def _has_fx_context_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.transaction_fx_rate is not None or bool(row.fx_contract_id)


_COMPONENT_FAMILY_PREDICATES: tuple[tuple[str, _ComponentPredicate], ...] = (
    ("cashflow", _has_cashflow_component),
    ("fee", _has_fee_component),
    ("income", _has_income_component),
    ("tax", _has_tax_component),
    ("realized_capital_pnl", _has_realized_capital_pnl_component),
    ("realized_fx_pnl", _has_realized_fx_pnl_component),
    ("realized_total_pnl", _has_realized_total_pnl_component),
    ("fx_context", _has_fx_context_component),
)


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
