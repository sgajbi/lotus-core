from decimal import Decimal

from src.services.query_service.app.advisory_simulation.common.intent_dependencies import (
    link_buy_intent_dependencies,
)
from src.services.query_service.app.advisory_simulation.common.simulation_shared import (
    apply_fx_spot_to_portfolio,
    apply_security_trade_to_portfolio,
    quantize_amount_for_currency,
)
from src.services.query_service.app.advisory_simulation.models import (
    FxSpotIntent,
    Money,
    SecurityTradeIntent,
)
from tests.shared.factories import cash, portfolio_snapshot


def test_link_buy_intent_dependencies_skips_missing_notional_and_avoids_duplicates() -> None:
    buy_without_notional = SecurityTradeIntent(
        intent_id="buy_1",
        instrument_id="EQ_1",
        side="BUY",
        quantity=Decimal("1"),
        notional=None,
    )
    sell = SecurityTradeIntent(
        intent_id="sell_1",
        instrument_id="EQ_2",
        side="SELL",
        quantity=Decimal("1"),
        notional=Money(amount=Decimal("100"), currency="USD"),
    )
    buy_with_notional = SecurityTradeIntent(
        intent_id="buy_2",
        instrument_id="EQ_3",
        side="BUY",
        quantity=Decimal("1"),
        notional=Money(amount=Decimal("100"), currency="USD"),
        dependencies=["fx_1"],
    )

    intents = [buy_without_notional, sell, buy_with_notional]
    link_buy_intent_dependencies(
        intents,
        fx_intent_id_by_currency={"USD": "fx_1"},
        include_same_currency_sell_dependency=True,
    )

    assert buy_without_notional.dependencies == []
    assert buy_with_notional.dependencies == ["fx_1", "sell_1"]


def test_apply_trade_and_fx_helpers_respect_guard_clauses_and_currency_rounding() -> None:
    portfolio = portfolio_snapshot(cash_balances=[cash("USD", "1000")])
    incomplete_buy = SecurityTradeIntent(
        intent_id="buy_1",
        instrument_id="EQ_1",
        side="BUY",
        quantity=None,
        notional=Money(amount=Decimal("100"), currency="USD"),
    )

    apply_security_trade_to_portfolio(portfolio, incomplete_buy)
    assert portfolio.positions == []

    fx_intent = FxSpotIntent(
        intent_id="fx_1",
        pair="USD/JPY",
        buy_currency="JPY",
        buy_amount=Decimal("1000"),
        sell_currency="USD",
        sell_amount_estimated=Decimal("10"),
    )
    apply_fx_spot_to_portfolio(portfolio, fx_intent)

    usd_cash = next(
        cash_balance
        for cash_balance in portfolio.cash_balances
        if cash_balance.currency == "USD"
    )
    jpy_cash = next(
        cash_balance
        for cash_balance in portfolio.cash_balances
        if cash_balance.currency == "JPY"
    )

    assert usd_cash.amount == Decimal("990")
    assert jpy_cash.amount == Decimal("1000")
    assert quantize_amount_for_currency(Decimal("1.6"), "JPY") == Decimal("2")
    assert quantize_amount_for_currency(Decimal("1.2345"), "BHD") == Decimal("1.234")
