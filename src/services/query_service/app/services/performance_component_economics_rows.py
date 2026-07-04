from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..dtos.reference_integration_dto import (
    PerformanceComponentEconomicsFeeComponent,
    PerformanceComponentEconomicsRow,
)
from ..read_models import (
    PerformanceEconomicsCostReadRecord,
    PerformanceEconomicsTransactionReadRecord,
)
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from .decimal_amounts import decimal_or_zero
from .performance_component_economics_policy import (
    performance_component_economics_source_lineage,
)


def build_performance_component_economics_rows(
    transactions: list[PerformanceEconomicsTransactionReadRecord],
) -> list[PerformanceComponentEconomicsRow]:
    return [_performance_component_economics_row(transaction) for transaction in transactions]


def _performance_component_economics_row(
    transaction: PerformanceEconomicsTransactionReadRecord,
) -> PerformanceComponentEconomicsRow:
    cashflow = transaction.cashflow
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
        cashflow_amount=(decimal_or_zero(cashflow.amount) if cashflow is not None else None),
        cashflow_currency=(
            str(cashflow.currency).strip().upper() if cashflow is not None else None
        ),
        cashflow_classification=(
            str(cashflow.classification).strip().upper() if cashflow is not None else None
        ),
        cashflow_timing=(str(cashflow.timing).strip().upper() if cashflow is not None else None),
        is_position_flow=bool(cashflow.is_position_flow) if cashflow is not None else None,
        is_portfolio_flow=bool(cashflow.is_portfolio_flow) if cashflow is not None else None,
        withholding_tax_amount=decimal_or_zero(transaction.withholding_tax_amount),
        other_interest_deductions_amount=decimal_or_zero(
            transaction.other_interest_deductions_amount
        ),
        net_interest_amount=decimal_or_zero(transaction.net_interest_amount),
        realized_capital_pnl_local=decimal_or_zero(transaction.realized_capital_pnl_local),
        realized_fx_pnl_local=decimal_or_zero(transaction.realized_fx_pnl_local),
        realized_total_pnl_local=decimal_or_zero(transaction.realized_total_pnl_local),
        realized_pnl_local_currency=_transaction_trade_currency(transaction),
        realized_capital_pnl_base=decimal_or_zero(transaction.realized_capital_pnl_base),
        realized_fx_pnl_base=decimal_or_zero(transaction.realized_fx_pnl_base),
        realized_total_pnl_base=decimal_or_zero(transaction.realized_total_pnl_base),
        transaction_fx_rate=transaction.transaction_fx_rate,
        fx_contract_id=transaction.fx_contract_id,
        source_lineage=performance_component_economics_source_lineage(),
    )


def _transaction_fee_components(
    transaction: PerformanceEconomicsTransactionReadRecord,
) -> list[PerformanceComponentEconomicsFeeComponent]:
    costs = [
        cost
        for cost in _unique_transaction_cost_components(transaction)
        if decimal_or_zero(cost.amount) > 0
    ]
    if costs:
        grouped: dict[str, list[Decimal]] = defaultdict(list)
        for cost in costs:
            grouped[
                normalize_currency_code(cost.currency or _transaction_trade_currency(transaction))
            ].append(decimal_or_zero(cost.amount))
        return [
            PerformanceComponentEconomicsFeeComponent(
                currency=currency,
                amount=sum(amounts, Decimal("0")),
                evidence_count=len(amounts),
            )
            for currency, amounts in sorted(grouped.items())
        ]

    trade_fee = _transaction_fee_amount(transaction)
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


def _unique_transaction_cost_components(
    transaction: PerformanceEconomicsTransactionReadRecord,
) -> list[PerformanceEconomicsCostReadRecord]:
    unique_costs: list[PerformanceEconomicsCostReadRecord] = []
    observed_keys: set[tuple[str, str, str]] = set()
    for index, cost in enumerate(transaction.costs):
        component_key = _transaction_cost_component_identity(
            transaction=transaction,
            cost=cost,
            fallback_sequence=index,
        )
        if component_key in observed_keys:
            continue
        observed_keys.add(component_key)
        unique_costs.append(cost)
    return unique_costs


def _transaction_cost_component_identity(
    *,
    transaction: PerformanceEconomicsTransactionReadRecord,
    cost: PerformanceEconomicsCostReadRecord,
    fallback_sequence: int,
) -> tuple[str, str, str]:
    fee_type = str(cost.fee_type or "").strip().lower()
    cost_currency = cost.currency or transaction.trade_currency or transaction.currency
    if fee_type and cost_currency:
        return ("component", fee_type, normalize_currency_code(cost_currency))
    return ("anonymous", str(fallback_sequence), "")


def _transaction_fee_amount(transaction: PerformanceEconomicsTransactionReadRecord) -> Decimal:
    costs = _unique_transaction_cost_components(transaction)
    if costs:
        return sum((decimal_or_zero(cost.amount) for cost in costs), Decimal("0"))
    return decimal_or_zero(transaction.trade_fee)


def _transaction_trade_currency(transaction: PerformanceEconomicsTransactionReadRecord) -> str:
    trade_currency = transaction.trade_currency
    if trade_currency:
        return normalize_currency_code(trade_currency)
    return normalize_currency_code(transaction.currency)
