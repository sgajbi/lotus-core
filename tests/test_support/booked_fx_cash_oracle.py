"""Independent exact financial oracle for the supported booked-FX cash fixture."""

import re
from decimal import Decimal

FIRST_DAY, LAST_DAY = "2026-04-09", "2026-04-10"


def decimal(value):
    assert value is not None and not isinstance(value, bool)
    number = Decimal(str(value))
    assert number.is_finite()
    return number


def _assert_holdings_authority(body, portfolio, day):
    assert body["portfolio_id"] == portfolio and body["as_of_date"] == day
    assert body["data_quality_status"] == body["reconciliation_status"] == "COMPLETE"
    assert body["freshness_status"] == "CURRENT" and body["source_evidence_current"] is True
    assert body["degradation"]["reason_codes"] == []
    assert body["source_refs"] == [f"lotus-core://source/HoldingsAsOf/{portfolio}/{day}"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", body["content_hash"])
    assert body["content_hash"] == body["source_digest"]


def assert_qualified_holdings(body, *, portfolio, equity, cash, day, reference_fx):
    """No calculator reuse, status override, null default or expected-value rounding."""
    fx = Decimal(reference_fx)
    price = Decimal("100" if day == FIRST_DAY else "110")
    _assert_holdings_authority(body, portfolio, day)
    rows = {row["security_id"]: row for row in body["positions"]}
    assert len(body["positions"]) == 2 and set(rows) == {equity, cash}
    for security, quantity, local_basis, local_mark in (
        (equity, Decimal("10"), Decimal("1000"), Decimal("10") * price),
        (cash, Decimal("-1000"), Decimal("-1000"), Decimal("-1000")),
    ):
        row = rows[security]
        value = row["valuation"]
        assert row["position_date"] == day and row["currency"] == "XTS"
        assert row["reprocessing_status"] == "CURRENT"
        assert decimal(row["quantity"]) == quantity
        assert decimal(row["cost_basis_local"]) == local_basis
        assert decimal(row["cost_basis"]) == local_basis * Decimal("2")
        assert decimal(value["market_price"]) == (price if security == equity else 1)
        assert decimal(value["market_value_local"]) == local_mark
        assert decimal(value["market_value"]) == local_mark * fx
        assert decimal(value["unrealized_gain_loss_local"]) == local_mark - local_basis
        price_gain = (local_mark - local_basis) * fx
        fx_gain = local_basis * (fx - Decimal("2"))
        assert decimal(value["unrealized_price_gain_loss"]) == price_gain
        assert decimal(value["unrealized_fx_gain_loss"]) == fx_gain
        assert decimal(value["unrealized_gain_loss"]) == price_gain + fx_gain
    net_mark = Decimal("10") * (price - Decimal("100")) * fx
    assert sum(decimal(row["valuation"]["market_value"]) for row in rows.values()) == net_mark
    assert (
        sum(decimal(row["valuation"]["unrealized_gain_loss"]) for row in rows.values()) == net_mark
    )


def has_qualified_holdings(body, **scope):
    try:
        assert_qualified_holdings(body, **scope)
    except (AssertionError, KeyError, TypeError, ValueError, ArithmeticError):
        return False
    return True


def assert_missing_valuation_fx(body, *, portfolio, equity, cash):
    """Require unavailable valuation lineage; producing jobs separately identify missing FX."""
    assert body["portfolio_id"] == portfolio and body["as_of_date"] == LAST_DAY
    assert body["data_quality_status"] != "COMPLETE"
    assert "VALUATION_CURRENCY_LINEAGE_MISSING" in body["degradation"]["reason_codes"]
    rows = {row["security_id"]: row for row in body["positions"]}
    assert len(body["positions"]) == 2 and set(rows) == {equity, cash}
    for security, basis in ((equity, "2000"), (cash, "-2000")):
        row = rows[security]
        assert decimal(row["cost_basis"]) == Decimal(basis)
        assert row["valuation"]["market_value"] is None
        assert row["valuation"]["unrealized_gain_loss"] is None


def has_missing_valuation_fx(body, **scope):
    try:
        assert_missing_valuation_fx(body, **scope)
    except (AssertionError, KeyError, TypeError, ValueError, ArithmeticError):
        return False
    return True


def assert_linked_transactions(body, *, buy_id, equity, cash):
    rows = body["transactions"]
    assert len(rows) == 2
    by_id = {row["transaction_id"]: row for row in rows}
    assert set(by_id) == {buy_id, f"{buy_id}-CASHLEG"}
    parent, child = by_id[buy_id], by_id[f"{buy_id}-CASHLEG"]
    assert parent["security_id"] == equity and child["security_id"] == cash
    assert child["originating_transaction_id"] == buy_id
    assert parent["cash_entry_mode"] == "AUTO_GENERATE"
    for row in rows:
        assert decimal(row["transaction_fx_rate"]) == Decimal("2")
    return by_id


def assert_portfolio_marks(body, *, last_fx):
    """Two-day equity-plus-negative-cash net wealth; no external funding flow."""
    assert body["data_quality_status"] == "COMPLETE"
    assert body["freshness_status"] == "CURRENT" and body["source_evidence_current"] is True
    assert body["reporting_currency"] == body["portfolio_currency"] == "USD"
    assert body["page"]["next_page_token"] is None
    rows = body["observations"]
    assert len(rows) == 2
    assert [row["valuation_date"] for row in rows] == [FIRST_DAY, LAST_DAY]
    assert [decimal(row["ending_market_value"]) for row in rows] == [
        Decimal("0"),
        Decimal("100") * Decimal(last_fx),
    ]
    assert [decimal(row["beginning_market_value"]) for row in rows] == [Decimal("0")] * 2
    assert all(row["valuation_status"] in {"final", "restated"} for row in rows)


def has_portfolio_marks(body, *, last_fx):
    try:
        assert_portfolio_marks(body, last_fx=last_fx)
    except (AssertionError, KeyError, TypeError, ValueError, ArithmeticError):
        return False
    return True


def assert_funded_cash_holdings(body, *, portfolio, equity, cash, stage):
    """Literal FIFO book at valuation FX3, with booked FX2 and fees in XTS."""
    _assert_holdings_authority(body, portfolio, LAST_DAY)
    rows = {row["security_id"]: row for row in body["positions"]}
    assert len(body["positions"]) == 2 and set(rows) == {equity, cash}
    # quantity, local cost, base cost, local mark, base mark, local P&L, base P&L, price, FX
    literals = {
        "funded_buy": (
            ("10", "1000", "2000", "1100", "3300", "100", "1300", "300", "1000"),
            ("1000", "1000", "2000", "1000", "3000", "0", "1000", "0", "1000"),
        ),
        "funded_fee_buy": (
            ("11", "1102", "2204", "1210", "3630", "108", "1426", "324", "1102"),
            ("898", "898", "1796", "898", "2694", "0", "898", "0", "898"),
        ),
        "funded_sell": (
            ("6", "602", "1204", "660", "1980", "58", "776", "174", "602"),
            ("1446", "1446", "2892", "1446", "4338", "0", "1446", "0", "1446"),
        ),
        "funded_income": (
            ("6", "602", "1204", "660", "1980", "58", "776", "174", "602"),
            ("1544", "1544", "3088", "1544", "4632", "0", "1544", "0", "1544"),
        ),
        "funded_interest": (
            ("6", "602", "1204", "660", "1980", "58", "776", "174", "602"),
            ("1592", "1592", "3184", "1592", "4776", "0", "1592", "0", "1592"),
        ),
    }
    for security, expected in zip((equity, cash), literals[stage], strict=True):
        row = rows[security]
        assert row["currency"] == "XTS" and row["position_date"] == LAST_DAY
        assert row["reprocessing_status"] == "CURRENT"
        valuation = row["valuation"]
        actual = [row["quantity"], row["cost_basis_local"], row["cost_basis"]] + [
            valuation[field]
            for field in (
                "market_value_local",
                "market_value",
                "unrealized_gain_loss_local",
                "unrealized_gain_loss",
                "unrealized_price_gain_loss",
                "unrealized_fx_gain_loss",
            )
        ]
        assert [decimal(value) for value in actual] == [Decimal(value) for value in expected]
        assert decimal(valuation["market_price"]) == Decimal("110" if security == equity else "1")
    total_mark, total_pnl = {
        "funded_buy": ("6300", "2300"),
        "funded_fee_buy": ("6324", "2324"),
        "funded_sell": ("6318", "2222"),
        "funded_income": ("6612", "2320"),
        "funded_interest": ("6756", "2368"),
    }[stage]
    assert sum(decimal(row["valuation"]["market_value"]) for row in rows.values()) == Decimal(
        total_mark
    )
    assert sum(
        decimal(row["valuation"]["unrealized_gain_loss"]) for row in rows.values()
    ) == Decimal(total_pnl)


def has_funded_cash_holdings(body, **scope):
    try:
        assert_funded_cash_holdings(body, **scope)
    except (AssertionError, KeyError, TypeError, ValueError, ArithmeticError):
        return False
    return True


def assert_same_currency_funded_holdings(body, *, portfolio, equity, cash):
    """USD identity control: independent literals, not a foreign-FX oracle rescaling."""
    _assert_holdings_authority(body, portfolio, LAST_DAY)
    rows = {row["security_id"]: row for row in body["positions"]}
    assert len(body["positions"]) == 2 and set(rows) == {equity, cash}
    for security, quantity, mark, gain in (
        (equity, "10", "1100", "100"),
        (cash, "1000", "1000", "0"),
    ):
        row = rows[security]
        assert row["currency"] == "USD" and row["position_date"] == LAST_DAY
        assert row["reprocessing_status"] == "CURRENT"
        assert decimal(row["quantity"]) == Decimal(quantity)
        assert decimal(row["cost_basis_local"]) == decimal(row["cost_basis"]) == Decimal("1000")
        value = row["valuation"]
        assert decimal(value["market_price"]) == Decimal("110" if security == equity else "1")
        assert (
            decimal(value["market_value_local"]) == decimal(value["market_value"]) == Decimal(mark)
        )
        assert (
            decimal(value["unrealized_gain_loss_local"])
            == decimal(value["unrealized_gain_loss"])
            == decimal(value["unrealized_price_gain_loss"])
            == Decimal(gain)
        )
        assert decimal(value["unrealized_fx_gain_loss"]) == Decimal("0")
    assert sum(decimal(row["valuation"]["market_value"]) for row in rows.values()) == Decimal(
        "2100"
    )
    assert sum(
        decimal(row["valuation"]["unrealized_gain_loss"]) for row in rows.values()
    ) == Decimal("100")


def has_same_currency_funded_holdings(body, **scope):
    try:
        assert_same_currency_funded_holdings(body, **scope)
    except (AssertionError, KeyError, TypeError, ValueError, ArithmeticError):
        return False
    return True


def assert_funded_cash_transactions(body, scenario):
    buy_id = scenario["buy_id"]
    rows = body["transactions"]
    by_id = {row["transaction_id"]: row for row in rows}
    parents = (
        buy_id,
        f"{buy_id}-FEE-BUY",
        f"{buy_id}-SELL",
        f"{buy_id}-DIVIDEND",
        f"{buy_id}-INTEREST",
    )
    assert len(rows) == 11 and set(by_id) == {
        f"{buy_id}-FUND",
        *parents,
        *(f"{parent}-CASHLEG" for parent in parents),
    }
    assert decimal(by_id[f"{buy_id}-SELL"]["realized_gain_loss_local"]) == Decimal("48")
    assert decimal(by_id[f"{buy_id}-SELL"]["realized_gain_loss"]) == Decimal("96")
    for parent, amount, direction in zip(
        parents,
        ("1000", "102", "548", "98", "48"),
        ("OUTFLOW", "OUTFLOW", "INFLOW", "INFLOW", "INFLOW"),
        strict=True,
    ):
        child = by_id[f"{parent}-CASHLEG"]
        assert child["originating_transaction_id"] == parent
        assert child["security_id"] == scenario["cash"]
        assert child["settlement_cash_account_id"] == scenario["cash"]
        assert child["movement_direction"] == direction
        assert decimal(child["gross_transaction_amount"]) == Decimal(amount)
        assert decimal(child["trade_fee"]) == Decimal("0")
        day = FIRST_DAY if parent == buy_id else LAST_DAY
        assert child["transaction_date"][:10] == child["settlement_date"][:10] == day
    for parent in parents[1:]:
        assert decimal(by_id[parent]["trade_fee"]) == Decimal("2")
        assert by_id[parent]["trade_currency"] == "XTS"
    for row in rows:
        assert decimal(row["transaction_fx_rate"]) == Decimal("2")
