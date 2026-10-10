"""Independent exact financial oracle for the supported booked-FX cash fixture."""

import re
from decimal import Decimal

FIRST_DAY, LAST_DAY = "2026-04-09", "2026-04-10"


def decimal(value):
    assert value is not None and not isinstance(value, bool)
    number = Decimal(str(value))
    assert number.is_finite()
    return number


def assert_qualified_holdings(body, *, portfolio, equity, cash, day, reference_fx):
    """No calculator reuse, status override, null default or expected-value rounding."""
    fx = Decimal(reference_fx)
    price = Decimal("100" if day == FIRST_DAY else "110")
    assert body["portfolio_id"] == portfolio and body["as_of_date"] == day
    assert body["data_quality_status"] == body["reconciliation_status"] == "COMPLETE"
    assert body["freshness_status"] == "CURRENT" and body["source_evidence_current"] is True
    assert body["degradation"]["reason_codes"] == []
    assert body["source_refs"] == [f"lotus-core://source/HoldingsAsOf/{portfolio}/{day}"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", body["content_hash"])
    assert body["content_hash"] == body["source_digest"]
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
