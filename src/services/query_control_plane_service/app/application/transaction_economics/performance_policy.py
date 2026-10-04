"""Supportability and aggregation policy for performance economics."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Callable, cast

from ...contracts.performance_component_economics import (
    SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES,
    PerformanceComponentEconomicsRow,
    PerformanceComponentEconomicsTotal,
)
from ...domain.transaction_economics import BookedTransactionEconomics
from .evidence import latest_evidence_timestamp

SOURCE_CONTRACT_VERSION = "performance_component_economics_v1"
SOURCE_LINEAGE = {
    "source_system": "transactions",
    "source_table": "transactions,cashflows,transaction_costs,portfolios,outbox_events",
    "contract_version": SOURCE_CONTRACT_VERSION,
}

_ComponentPredicate = Callable[[PerformanceComponentEconomicsRow], bool]


def performance_component_economics_source_lineage() -> dict[str, str]:
    return dict(SOURCE_LINEAGE)


def performance_component_economics_supportability_state(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
    is_initial_page: bool,
) -> str:
    if not rows:
        return "READY" if is_initial_page else "UNAVAILABLE"
    if has_more:
        return "DEGRADED"
    if _has_incomplete_fx_evidence(rows):
        return "DEGRADED"
    return "READY"


def performance_component_economics_supportability_reason(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
    is_initial_page: bool,
) -> str:
    if not rows:
        if is_initial_page:
            return "PERFORMANCE_COMPONENT_ECONOMICS_NO_ACTIVITY"
        return "PERFORMANCE_COMPONENT_ECONOMICS_PAGE_EVIDENCE_CHANGED"
    if has_more:
        return "PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL"
    if _has_incomplete_fx_evidence(rows):
        return "PERFORMANCE_COMPONENT_ECONOMICS_FX_SOURCE_INCOMPLETE"
    return "PERFORMANCE_COMPONENT_ECONOMICS_READY"


def performance_component_economics_data_quality_status(
    *,
    rows: list[PerformanceComponentEconomicsRow],
    has_more: bool,
    is_initial_page: bool,
) -> str:
    if not rows and not is_initial_page:
        return "UNKNOWN"
    if has_more or _has_incomplete_fx_evidence(rows):
        return "PARTIAL"
    return "COMPLETE"


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
    rows: list[PerformanceComponentEconomicsRow],
    observed_component_families: list[str],
    *,
    authoritative_empty: bool,
) -> list[str]:
    if authoritative_empty:
        return []
    return [
        family
        for family in SUPPORTED_PERFORMANCE_ECONOMICS_COMPONENT_FAMILIES
        if family not in observed_component_families
        or (
            family in {"realized_fx_pnl", "realized_total_pnl"}
            and _has_incomplete_fx_evidence(rows)
        )
    ]


def build_performance_component_economics_totals(
    rows: list[PerformanceComponentEconomicsRow],
    *,
    portfolio_base_currency: str,
) -> list[PerformanceComponentEconomicsTotal]:
    grouped: dict[tuple[str, str], list[Decimal | None]] = defaultdict(list)
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
        _append_total(
            grouped,
            "realized_fx_pnl",
            portfolio_base_currency,
            row.realized_fx_pnl_base,
            retain_zero=(
                row.fx_pnl_evidence_reason in {"FX_SOURCE_QUALIFIED", "FX_SOURCE_INCOMPLETE"}
                and row.realized_fx_pnl_base is not None
            ),
        )
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
            amount=(
                None
                if None in amounts
                else sum((amount for amount in amounts if amount is not None), Decimal("0"))
            ),
            evidence_count=sum(amount is not None for amount in amounts),
            missing_evidence_count=sum(amount is None for amount in amounts),
        )
        for (component_family, currency), amounts in sorted(grouped.items())
    ]


def latest_performance_evidence_timestamp(
    transactions: list[BookedTransactionEconomics],
):
    return latest_evidence_timestamp(transactions)


def _append_total(
    grouped: dict[tuple[str, str], list[Decimal | None]],
    component_family: str,
    currency: str,
    amount: Decimal | None,
    *,
    retain_zero: bool = False,
) -> None:
    if amount != 0 or retain_zero:
        grouped[(component_family, currency)].append(amount)


def _has_incomplete_fx_evidence(rows: list[PerformanceComponentEconomicsRow]) -> bool:
    return any(
        row.fx_pnl_evidence_reason in {"FX_SOURCE_INCOMPLETE", "FX_SOURCE_AUTHORITY_UNAVAILABLE"}
        for row in rows
    )


def _observed_row_component_families(row: PerformanceComponentEconomicsRow) -> set[str]:
    return {family for family, predicate in _COMPONENT_FAMILY_PREDICATES if predicate(row)}


def _has_cashflow_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.cashflow_amount not in (None, Decimal("0"))


def _has_fee_component(row: PerformanceComponentEconomicsRow) -> bool:
    return bool(row.trade_fee_components) or row.trade_fee_amount != 0


def _has_income_component(row: PerformanceComponentEconomicsRow) -> bool:
    return cast(bool, row.net_interest_amount != 0)


def _has_tax_component(row: PerformanceComponentEconomicsRow) -> bool:
    return cast(bool, row.withholding_tax_amount != 0 or row.other_interest_deductions_amount != 0)


def _has_realized_capital_pnl_component(row: PerformanceComponentEconomicsRow) -> bool:
    return cast(bool, row.realized_capital_pnl_local != 0 or row.realized_capital_pnl_base != 0)


def _has_realized_fx_pnl_component(row: PerformanceComponentEconomicsRow) -> bool:
    if row.fx_pnl_evidence_reason != "FX_SOURCE_NOT_APPLICABLE":
        return row.realized_fx_pnl_local is not None and row.realized_fx_pnl_base is not None
    return cast(bool, row.realized_fx_pnl_local != 0 or row.realized_fx_pnl_base != 0)


def _has_realized_total_pnl_component(row: PerformanceComponentEconomicsRow) -> bool:
    return row.realized_total_pnl_local not in (
        None,
        Decimal("0"),
    ) or row.realized_total_pnl_base not in (None, Decimal("0"))


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
