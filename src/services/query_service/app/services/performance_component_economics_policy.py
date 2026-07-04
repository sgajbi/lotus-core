from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Callable

from ..dtos.reference_integration_dto import (
    SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES,
    PerformanceComponentEconomicsRow,
    PerformanceComponentEconomicsTotal,
)
from ..read_models import PerformanceEconomicsTransactionReadRecord
from .reference_data_helpers import latest_reference_evidence_timestamp

SOURCE_CONTRACT_VERSION = "performance_component_economics_v1"
SOURCE_LINEAGE = {
    "source_system": "transactions",
    "source_table": "transactions,cashflows,transaction_costs",
    "contract_version": SOURCE_CONTRACT_VERSION,
}

_ComponentPredicate = Callable[[PerformanceComponentEconomicsRow], bool]


def performance_component_economics_source_lineage() -> dict[str, str]:
    return dict(SOURCE_LINEAGE)


def performance_component_economics_supportability_state(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
) -> str:
    if not rows:
        return "UNAVAILABLE"
    if has_more:
        return "DEGRADED"
    return "READY"


def performance_component_economics_supportability_reason(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
) -> str:
    if not rows:
        return "PERFORMANCE_COMPONENT_ECONOMICS_EVIDENCE_NOT_FOUND"
    if has_more:
        return "PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL"
    return "PERFORMANCE_COMPONENT_ECONOMICS_READY"


def performance_component_economics_data_quality_status(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
) -> str:
    if has_more:
        return "PARTIAL"
    if rows:
        return "COMPLETE"
    return "UNKNOWN"


def observed_performance_component_families(
    rows: list[PerformanceComponentEconomicsRow],
) -> list[str]:
    observed: set[str] = set()
    for row in rows:
        observed.update(_observed_row_component_families(row))
    return [
        family
        for family in SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES
        if family in observed
    ]


def missing_performance_component_families(
    observed_component_families: list[str],
) -> list[str]:
    return [
        family
        for family in SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES
        if family not in observed_component_families
    ]


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


def latest_performance_evidence_timestamp(
    transactions: list[PerformanceEconomicsTransactionReadRecord],
):
    evidence_rows: list[object] = []
    for transaction in transactions:
        evidence_rows.append(transaction)
        if transaction.cashflow is not None:
            evidence_rows.append(transaction.cashflow)
        evidence_rows.extend(transaction.costs)
    return latest_reference_evidence_timestamp(evidence_rows)


def _append_total(
    grouped: dict[tuple[str, str], list[Decimal]],
    component_family: str,
    currency: str,
    amount: Decimal,
) -> None:
    if amount != 0:
        grouped[(component_family, currency)].append(amount)


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
