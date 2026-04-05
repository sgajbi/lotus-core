"""
FILE: src/core/simulation_shared.py
"""

from decimal import Decimal
from typing import Literal

from src.services.query_service.app.advisory_simulation.models import (
    CashBalance,
    Money,
    PortfolioSnapshot,
    Position,
    ProposalOrderIntent,
    Reconciliation,
    RuleResult,
    SecurityTradeIntent,
)
from src.services.query_service.app.advisory_simulation.precision_policy import to_decimal

_CURRENCY_MINOR_UNITS = {
    "BHD": 3,
    "JPY": 0,
    "KRW": 0,
    "KWD": 3,
    "OMR": 3,
    "VND": 0,
}


def ensure_position(portfolio: PortfolioSnapshot, instrument_id: str) -> Position:
    position = next(
        (item for item in portfolio.positions if item.instrument_id == instrument_id), None
    )
    if not position:
        position = Position(instrument_id=instrument_id, quantity=Decimal("0"))
        portfolio.positions.append(position)
    return position


def ensure_cash_balance(portfolio: PortfolioSnapshot, currency: str) -> CashBalance:
    cash_balance = next(
        (item for item in portfolio.cash_balances if item.currency == currency), None
    )
    if not cash_balance:
        cash_balance = CashBalance(currency=currency, amount=Decimal("0"))
        portfolio.cash_balances.append(cash_balance)
    return cash_balance


def apply_security_trade_to_portfolio(
    portfolio: PortfolioSnapshot, intent: SecurityTradeIntent
) -> None:
    if intent.notional is None or intent.quantity is None:
        return
    position = ensure_position(portfolio, intent.instrument_id)
    cash_balance = ensure_cash_balance(portfolio, intent.notional.currency)

    if intent.side == "BUY":
        position.quantity += intent.quantity
        cash_balance.amount -= intent.notional.amount
    else:
        position.quantity -= intent.quantity
        cash_balance.amount += intent.notional.amount


def apply_fx_spot_to_portfolio(portfolio: PortfolioSnapshot, intent: ProposalOrderIntent) -> None:
    if intent.intent_type != "FX_SPOT":
        return
    ensure_cash_balance(portfolio, intent.sell_currency).amount -= intent.sell_amount_estimated
    ensure_cash_balance(portfolio, intent.buy_currency).amount += intent.buy_amount


def quantize_amount_for_currency(amount: Decimal, currency: str) -> Decimal:
    digits = _CURRENCY_MINOR_UNITS.get(currency, 2)
    quantum = Decimal("1") if digits == 0 else Decimal(f"1e-{digits}")
    return to_decimal(amount).quantize(quantum)


def sort_execution_intents(intents: list[ProposalOrderIntent]) -> list[ProposalOrderIntent]:
    def _sort_key(intent: ProposalOrderIntent) -> int:
        if intent.intent_type == "CASH_FLOW":
            return 0
        if intent.intent_type == "SECURITY_TRADE":
            if intent.side == "SELL":
                return 1
            return 3
        return 2

    return sorted(intents, key=_sort_key)


def derive_status_from_rules(
    rule_results: list[RuleResult],
) -> Literal["READY", "BLOCKED", "PENDING_REVIEW"]:
    has_hard_fail = any(rule.severity == "HARD" and rule.status == "FAIL" for rule in rule_results)
    if has_hard_fail:
        return "BLOCKED"

    has_soft_fail = any(rule.severity == "SOFT" and rule.status == "FAIL" for rule in rule_results)
    if has_soft_fail:
        return "PENDING_REVIEW"

    return "READY"


def build_reconciliation(
    before_total: Decimal,
    after_total: Decimal,
    expected_after_total: Decimal,
    base_currency: str,
    *,
    use_absolute_scale: bool = False,
) -> tuple[Reconciliation, Decimal, Decimal]:
    recon_diff = abs(after_total - expected_after_total)
    scale_value = abs(expected_after_total) if use_absolute_scale else expected_after_total
    tolerance = Decimal("0.5") + (scale_value * Decimal("0.0005"))
    reconciliation = Reconciliation(
        before_total_value=Money(amount=before_total, currency=base_currency),
        after_total_value=Money(amount=after_total, currency=base_currency),
        delta=Money(amount=after_total - before_total, currency=base_currency),
        tolerance=Money(amount=tolerance, currency=base_currency),
        status="OK" if recon_diff <= tolerance else "MISMATCH",
    )
    return reconciliation, recon_diff, tolerance
