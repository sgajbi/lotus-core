from decimal import Decimal
from unittest.mock import patch

from src.services.query_service.app.advisory_simulation.advisory_engine import (
    run_proposal_simulation,
)
from src.services.query_service.app.advisory_simulation.models import (
    EngineOptions,
    Money,
    Reconciliation,
    SecurityTradeIntent,
)
from tests.shared.factories import (
    cash,
    market_data_snapshot,
    portfolio_snapshot,
    position,
    price,
    shelf_entry,
)


def _intent_types(result):
    return [intent.intent_type for intent in result.intents]


def test_proposal_simulation_generates_fx_funding_and_dependency():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_fx_1",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("SGD", "10000")],
    )
    market_data = market_data_snapshot(
        prices=[price("US_EQ", "100", "USD")],
        fx_rates=[{"pair": "USD/SGD", "rate": "1.35"}],
    )
    shelf = [shelf_entry("US_EQ", status="APPROVED")]
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "50"}],
        request_hash="proposal_hash_fx_dep",
    )

    assert result.status == "READY"
    assert _intent_types(result) == ["FX_SPOT", "SECURITY_TRADE"]
    fx_intent = result.intents[0]
    buy_intent = result.intents[1]
    assert fx_intent.pair == "USD/SGD"
    assert fx_intent.buy_amount == Decimal("5000.00")
    assert fx_intent.sell_amount_estimated == Decimal("6750.00")
    assert buy_intent.dependencies == [fx_intent.intent_id]


def test_proposal_simulation_supports_partial_funding_with_existing_foreign_cash():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_fx_2",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("SGD", "10000"), cash("USD", "500")],
    )
    market_data = market_data_snapshot(
        prices=[price("US_EQ", "100", "USD")],
        fx_rates=[{"pair": "USD/SGD", "rate": "1.35"}],
    )
    shelf = [shelf_entry("US_EQ", status="APPROVED")]
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "10"}],
        request_hash="proposal_hash_partial_fx",
    )

    assert result.status == "READY"
    assert _intent_types(result) == ["FX_SPOT", "SECURITY_TRADE"]
    fx_intent = result.intents[0]
    assert fx_intent.buy_amount == Decimal("500.00")
    assert fx_intent.sell_amount_estimated == Decimal("675.00")

    usd_cash = next(c for c in result.after_simulated.cash_balances if c.currency == "USD")
    assert usd_cash.amount == Decimal("0.00")
    assert result.diagnostics.funding_plan[0].fx_needed == Decimal("500.00")


def test_proposal_simulation_skips_fx_when_foreign_cash_already_sufficient():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_fx_3",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("SGD", "1000"), cash("USD", "1000")],
    )
    market_data = market_data_snapshot(
        prices=[price("US_EQ", "100", "USD")],
        fx_rates=[{"pair": "USD/SGD", "rate": "1.35"}],
    )
    shelf = [shelf_entry("US_EQ", status="APPROVED")]
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "5"}],
        request_hash="proposal_hash_no_fx_needed",
    )

    assert result.status == "READY"
    assert _intent_types(result) == ["SECURITY_TRADE"]
    buy_intent = result.intents[0]
    assert buy_intent.dependencies == []


def test_proposal_simulation_orders_intents_cashflow_sell_fx_buy():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_fx_4",
        base_currency="SGD",
        positions=[position("US_OLD", "10")],
        cash_balances=[cash("SGD", "1000")],
    )
    market_data = market_data_snapshot(
        prices=[
            price("US_OLD", "100", "USD"),
            price("US_NEW", "100", "USD"),
        ],
        fx_rates=[{"pair": "USD/SGD", "rate": "1.35"}],
    )
    shelf = [
        shelf_entry("US_OLD", status="APPROVED"),
        shelf_entry("US_NEW", status="APPROVED"),
    ]
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[{"currency": "SGD", "amount": "3000"}],
        proposed_trades=[
            {"side": "BUY", "instrument_id": "US_NEW", "quantity": "20"},
            {"side": "SELL", "instrument_id": "US_OLD", "quantity": "5"},
        ],
        request_hash="proposal_hash_ordering",
    )

    assert result.status == "READY"
    assert _intent_types(result) == ["CASH_FLOW", "SECURITY_TRADE", "FX_SPOT", "SECURITY_TRADE"]
    assert result.intents[1].side == "SELL"
    assert result.intents[2].intent_type == "FX_SPOT"
    assert result.intents[3].side == "BUY"


def test_proposal_simulation_can_link_buy_to_same_currency_sell_dependency():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_dep_toggle",
        base_currency="SGD",
        positions=[position("US_OLD", "10")],
        cash_balances=[cash("SGD", "1000")],
    )
    market_data = market_data_snapshot(
        prices=[
            price("US_OLD", "100", "USD"),
            price("US_NEW", "100", "USD"),
        ],
        fx_rates=[{"pair": "USD/SGD", "rate": "1.35"}],
    )
    shelf = [
        shelf_entry("US_OLD", status="APPROVED"),
        shelf_entry("US_NEW", status="APPROVED"),
    ]
    options = EngineOptions(
        enable_proposal_simulation=True,
        link_buy_to_same_currency_sell_dependency=True,
    )

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[{"currency": "SGD", "amount": "3000"}],
        proposed_trades=[
            {"side": "BUY", "instrument_id": "US_NEW", "quantity": "20"},
            {"side": "SELL", "instrument_id": "US_OLD", "quantity": "5"},
        ],
        request_hash="proposal_hash_ordering_dep_toggle",
    )

    sell_intent = next(
        intent
        for intent in result.intents
        if intent.intent_type == "SECURITY_TRADE" and intent.side == "SELL"
    )
    buy_intent = next(
        intent
        for intent in result.intents
        if intent.intent_type == "SECURITY_TRADE" and intent.side == "BUY"
    )
    assert sell_intent.intent_id in buy_intent.dependencies


def test_proposal_simulation_blocks_missing_fx_for_funding_when_blocking_enabled():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_fx_5",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("SGD", "10000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True, block_on_missing_fx=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
        request_hash="proposal_hash_missing_fx_block",
    )

    assert result.status == "BLOCKED"
    assert "USD/SGD" in result.diagnostics.missing_fx_pairs
    assert any(
        rule.reason_code == "PROPOSAL_MISSING_FX_FOR_FUNDING" for rule in result.rule_results
    )


def test_proposal_simulation_marks_pending_review_on_missing_fx_when_non_blocking():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_fx_6",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("SGD", "10000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True, block_on_missing_fx=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
        request_hash="proposal_hash_missing_fx_pending",
    )

    assert result.status == "PENDING_REVIEW"
    assert "USD/SGD" in result.diagnostics.missing_fx_pairs
    assert _intent_types(result) == []


def test_proposal_simulation_blocks_when_funding_cash_insufficient():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_fx_7",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("SGD", "100")],
    )
    market_data = market_data_snapshot(
        prices=[price("US_EQ", "100", "USD")],
        fx_rates=[{"pair": "USD/SGD", "rate": "1.35"}],
    )
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "2"}],
        request_hash="proposal_hash_insufficient_cash",
    )

    assert result.status == "BLOCKED"
    assert result.diagnostics.insufficient_cash
    assert any(
        rule.reason_code == "PROPOSAL_INSUFFICIENT_FUNDING_CASH" for rule in result.rule_results
    )


def test_proposal_simulation_blocks_notional_currency_mismatch():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_5b",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")], fx_rates=[])
    shelf = [shelf_entry("EQ_1", status="APPROVED")]
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[
            {
                "side": "BUY",
                "instrument_id": "EQ_1",
                "notional": {"amount": "200", "currency": "EUR"},
            }
        ],
        request_hash="proposal_hash_notional_currency_mismatch",
    )

    assert result.status == "BLOCKED"
    assert result.intents == []
    assert "PROPOSAL_INVALID_TRADE_INPUT" in result.diagnostics.warnings


def test_proposal_simulation_run_id_is_deterministic_for_request_hash():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_5c",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")], fx_rates=[])
    shelf = [shelf_entry("EQ_1", status="APPROVED")]
    options = EngineOptions(enable_proposal_simulation=True)
    proposed_trades = [{"side": "BUY", "instrument_id": "EQ_1", "quantity": "1"}]
    request_hash = "sha256:deterministic-hash"

    first = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=proposed_trades,
        request_hash=request_hash,
    )
    second = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=proposed_trades,
        request_hash=request_hash,
    )

    assert first.proposal_run_id == second.proposal_run_id


def test_proposal_simulation_notional_input_path_with_missing_base_fx_allowed():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6a",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True, block_on_missing_fx=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[
            {
                "side": "BUY",
                "instrument_id": "US_EQ",
                "notional": {"amount": "200", "currency": "USD"},
            }
        ],
        request_hash="proposal_hash_notional_missing_base_fx",
    )

    assert result.status == "READY"
    trade = next(intent for intent in result.intents if intent.intent_type == "SECURITY_TRADE")
    assert trade.quantity == Decimal("2")
    assert trade.notional_base is None
    assert "USD/SGD" in result.diagnostics.data_quality["fx_missing"]


def test_proposal_simulation_records_missing_price_non_blocking():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6b",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    options = EngineOptions(enable_proposal_simulation=True, block_on_missing_prices=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data_snapshot(prices=[], fx_rates=[]),
        shelf=[shelf_entry("EQ_404", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "EQ_404", "quantity": "1"}],
        request_hash="proposal_hash_missing_price_non_block",
    )

    assert result.status == "READY"
    assert "EQ_404" in result.diagnostics.data_quality["price_missing"]
    assert result.intents == []


def test_proposal_simulation_records_missing_fx_for_cash_flow_delta():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6c",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    options = EngineOptions(enable_proposal_simulation=True, block_on_missing_fx=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data_snapshot(prices=[], fx_rates=[]),
        shelf=[],
        options=options,
        proposed_cash_flows=[{"currency": "EUR", "amount": "100"}],
        proposed_trades=[],
        request_hash="proposal_hash_missing_fx_cash_delta",
    )

    assert result.status == "READY"
    assert "EUR/USD" in result.diagnostics.data_quality["fx_missing"]


def test_proposal_simulation_run_id_uses_random_prefix_without_hash():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6d",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data_snapshot(prices=[], fx_rates=[]),
        shelf=[],
        options=EngineOptions(enable_proposal_simulation=True),
        proposed_cash_flows=[],
        proposed_trades=[],
        request_hash="no_hash",
    )

    assert result.proposal_run_id.startswith("pr_")


def test_proposal_simulation_auto_funding_disabled_path_is_exercised():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6e",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True, auto_funding=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
        request_hash="proposal_hash_no_auto_funding",
    )

    assert result.status == "READY"
    assert _intent_types(result) == ["SECURITY_TRADE"]


def test_proposal_simulation_base_only_same_target_currency_blocks_if_cash_short():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6f",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "100"), cash("EUR", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(
        enable_proposal_simulation=True,
        fx_funding_source_currency="BASE_ONLY",
    )

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "2"}],
        request_hash="proposal_hash_base_only_same_ccy",
    )

    assert result.status == "BLOCKED"
    assert any(
        rule.reason_code == "PROPOSAL_INSUFFICIENT_FUNDING_CASH" for rule in result.rule_results
    )


def test_proposal_simulation_blocks_negative_cash_withdrawal():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6g",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    options = EngineOptions(enable_proposal_simulation=True, proposal_block_negative_cash=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data_snapshot(prices=[], fx_rates=[]),
        shelf=[],
        options=options,
        proposed_cash_flows=[{"currency": "USD", "amount": "-2000"}],
        proposed_trades=[],
        request_hash="proposal_hash_negative_withdrawal",
    )

    assert result.status == "BLOCKED"
    assert "PROPOSAL_WITHDRAWAL_NEGATIVE_CASH" in result.diagnostics.warnings


def test_proposal_simulation_records_missing_shelf_and_blocks():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6h",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
        request_hash="proposal_hash_missing_shelf",
    )

    assert result.status == "BLOCKED"
    assert "US_EQ" in result.diagnostics.data_quality["shelf_missing"]


def test_proposal_simulation_blocks_sell_only_buy():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6i",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="SELL_ONLY")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
        request_hash="proposal_hash_sell_only",
    )

    assert result.status == "BLOCKED"
    assert "PROPOSAL_TRADE_NOT_SUPPORTED_BY_SHELF" in result.diagnostics.warnings


def test_proposal_simulation_blocks_restricted_buy_when_not_allowed():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6j",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True, allow_restricted=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="RESTRICTED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
        request_hash="proposal_hash_restricted",
    )

    assert result.status == "BLOCKED"
    assert "PROPOSAL_TRADE_NOT_SUPPORTED_BY_SHELF" in result.diagnostics.warnings


def test_proposal_simulation_reconciliation_mismatch_blocks_run():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6k",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True)

    with patch(
        "src.services.query_service.app.advisory_simulation.advisory_engine.build_reconciliation",
        return_value=(
            Reconciliation(
                before_total_value=Money(amount=Decimal("1000"), currency="USD"),
                after_total_value=Money(amount=Decimal("900"), currency="USD"),
                delta=Money(amount=Decimal("-100"), currency="USD"),
                tolerance=Money(amount=Decimal("0"), currency="USD"),
                status="MISMATCH",
            ),
            Decimal("1"),
            Decimal("0"),
        ),
    ):
        result = run_proposal_simulation(
            portfolio=portfolio,
            market_data=market_data,
            shelf=[shelf_entry("EQ_1", status="APPROVED")],
            options=options,
            proposed_cash_flows=[],
            proposed_trades=[{"side": "BUY", "instrument_id": "EQ_1", "quantity": "1"}],
            request_hash="proposal_hash_recon_mismatch",
        )

    assert result.status == "BLOCKED"
    assert any(rule.rule_id == "RECONCILIATION" for rule in result.rule_results)


def test_proposal_simulation_non_blocking_missing_fx_records_data_quality_pair():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6l",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "0"), cash("EUR", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True, block_on_missing_fx=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=[shelf_entry("US_EQ", status="APPROVED")],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "5"}],
        request_hash="proposal_hash_missing_fx_pair_recorded",
    )

    assert result.status == "PENDING_REVIEW"
    assert "USD/EUR" in result.diagnostics.missing_fx_pairs
    assert "USD/EUR" in result.diagnostics.data_quality["fx_missing"]


def test_proposal_simulation_forces_pending_status_when_rule_derivation_returns_ready():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_6m",
        base_currency="SGD",
        positions=[],
        cash_balances=[cash("SGD", "10000")],
    )
    market_data = market_data_snapshot(prices=[price("US_EQ", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True, block_on_missing_fx=False)

    with patch(
        "src.services.query_service.app.advisory_simulation.advisory_engine.derive_status_from_rules",
        return_value="READY",
    ):
        result = run_proposal_simulation(
            portfolio=portfolio,
            market_data=market_data,
            shelf=[shelf_entry("US_EQ", status="APPROVED")],
            options=options,
            proposed_cash_flows=[],
            proposed_trades=[{"side": "BUY", "instrument_id": "US_EQ", "quantity": "1"}],
            request_hash="proposal_hash_force_pending",
        )

    assert result.status == "PENDING_REVIEW"


def test_proposal_simulation_adds_drift_analysis_with_reference_model():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_14c_a",
        base_currency="USD",
        positions=[position("EQ_OLD", "7"), position("BD_OLD", "2")],
        cash_balances=[cash("USD", "100")],
    )
    market_data = market_data_snapshot(
        prices=[
            price("EQ_OLD", "100", "USD"),
            price("BD_OLD", "100", "USD"),
            price("EQ_NEW", "100", "USD"),
        ],
        fx_rates=[],
    )
    shelf = [
        shelf_entry("EQ_OLD", status="APPROVED", asset_class="EQUITY"),
        shelf_entry("BD_OLD", status="APPROVED", asset_class="FIXED_INCOME"),
        shelf_entry("EQ_NEW", status="APPROVED", asset_class="EQUITY"),
    ]
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "EQ_NEW", "quantity": "1"}],
        reference_model={
            "model_id": "mdl_14c_1",
            "as_of": "2026-02-18",
            "base_currency": "USD",
            "asset_class_targets": [
                {"asset_class": "EQUITY", "weight": "0.60"},
                {"asset_class": "FIXED_INCOME", "weight": "0.35"},
                {"asset_class": "CASH", "weight": "0.05"},
            ],
        },
        request_hash="proposal_hash_14c_asset",
    )

    assert result.status == "READY"
    assert result.drift_analysis is not None
    assert result.drift_analysis.reference_model.model_id == "mdl_14c_1"
    assert result.drift_analysis.asset_class.drift_total_before == Decimal("0.15")
    assert result.drift_analysis.asset_class.drift_total_after == Decimal("0.20")
    assert result.drift_analysis.instrument is None


def test_proposal_simulation_adds_instrument_drift_when_targets_present():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_14c_b",
        base_currency="USD",
        positions=[position("EQ_A", "7"), position("EQ_B", "2")],
        cash_balances=[cash("USD", "100")],
    )
    market_data = market_data_snapshot(
        prices=[
            price("EQ_A", "100", "USD"),
            price("EQ_B", "100", "USD"),
            price("EQ_C", "100", "USD"),
        ],
        fx_rates=[],
    )
    shelf = [
        shelf_entry("EQ_A", status="APPROVED", asset_class="EQUITY"),
        shelf_entry("EQ_B", status="APPROVED", asset_class="EQUITY"),
        shelf_entry("EQ_C", status="APPROVED", asset_class="EQUITY"),
    ]
    options = EngineOptions(enable_proposal_simulation=True, enable_instrument_drift=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "EQ_C", "quantity": "1"}],
        reference_model={
            "model_id": "mdl_14c_2",
            "as_of": "2026-02-18",
            "base_currency": "USD",
            "asset_class_targets": [
                {"asset_class": "EQUITY", "weight": "0.95"},
                {"asset_class": "CASH", "weight": "0.05"},
            ],
            "instrument_targets": [
                {"instrument_id": "EQ_A", "weight": "0.40"},
                {"instrument_id": "EQ_B", "weight": "0.60"},
            ],
        },
        request_hash="proposal_hash_14c_instrument",
    )

    assert result.status == "READY"
    assert result.drift_analysis is not None
    assert result.drift_analysis.instrument is not None
    assert any(
        highlight.bucket == "EQ_C"
        for highlight in result.drift_analysis.highlights.unmodeled_exposures
    )


def test_proposal_simulation_skips_drift_analysis_on_reference_model_currency_mismatch():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_14c_c",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    options = EngineOptions(enable_proposal_simulation=True)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data_snapshot(prices=[], fx_rates=[]),
        shelf=[],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[],
        reference_model={
            "model_id": "mdl_14c_3",
            "as_of": "2026-02-18",
            "base_currency": "SGD",
            "asset_class_targets": [{"asset_class": "CASH", "weight": "1.0"}],
        },
        request_hash="proposal_hash_14c_currency_mismatch",
    )

    assert result.drift_analysis is None
    assert "REFERENCE_MODEL_BASE_CURRENCY_MISMATCH" in result.diagnostics.warnings


def test_proposal_simulation_includes_suitability_output_by_default():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_14d_a",
        base_currency="USD",
        positions=[position("EQ_A", "10")],
        cash_balances=[],
    )
    market_data = market_data_snapshot(
        prices=[
            price("EQ_A", "10", "USD"),
            price("EQ_B", "10", "USD"),
        ],
        fx_rates=[],
    )
    shelf = [
        shelf_entry("EQ_A", status="APPROVED", issuer_id="ISSUER_X", liquidity_tier="L1"),
        shelf_entry("EQ_B", status="APPROVED", issuer_id="ISSUER_Y", liquidity_tier="L2"),
    ]
    options = EngineOptions(
        enable_proposal_simulation=True,
        suitability_thresholds={
            "single_position_max_weight": "0.80",
            "issuer_max_weight": "1.0",
            "max_weight_by_liquidity_tier": {},
            "cash_band_min_weight": "0",
            "cash_band_max_weight": "1",
        },
    )

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data,
        shelf=shelf,
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[{"side": "BUY", "instrument_id": "EQ_B", "quantity": "1"}],
        request_hash="proposal_hash_14d_default_suitability",
    )

    assert result.suitability is not None
    assert result.suitability.summary.persistent_count == 1
    assert result.suitability.issues[0].issue_id == "SUIT_SINGLE_POSITION_MAX"
    assert result.suitability.recommended_gate == "NONE"


def test_proposal_simulation_can_disable_suitability_output():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_14d_b",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    options = EngineOptions(enable_proposal_simulation=True, enable_suitability_scanner=False)

    result = run_proposal_simulation(
        portfolio=portfolio,
        market_data=market_data_snapshot(prices=[], fx_rates=[]),
        shelf=[],
        options=options,
        proposed_cash_flows=[],
        proposed_trades=[],
        request_hash="proposal_hash_14d_disable_suitability",
    )

    assert result.suitability is None


def test_proposal_simulation_skips_buy_intent_without_notional():
    portfolio = portfolio_snapshot(
        portfolio_id="pf_prop_missing_notional_buy_intent",
        base_currency="USD",
        positions=[],
        cash_balances=[cash("USD", "1000")],
    )
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")], fx_rates=[])
    options = EngineOptions(enable_proposal_simulation=True)

    with (
        patch(
            "src.services.query_service.app.advisory_simulation.advisory_engine.build_proposal_security_trade_intent",
            return_value=(
                SecurityTradeIntent(
                    intent_id="oi_1",
                    instrument_id="EQ_1",
                    side="BUY",
                    quantity=Decimal("1"),
                    notional=None,
                ),
                None,
            ),
        ),
        patch(
            "src.services.query_service.app.advisory_simulation.advisory_engine.build_auto_funding_plan",
            return_value=([], {}, set(), [], False),
        ),
    ):
        result = run_proposal_simulation(
            portfolio=portfolio,
            market_data=market_data,
            shelf=[shelf_entry("EQ_1", status="APPROVED")],
            options=options,
            proposed_cash_flows=[],
            proposed_trades=[{"side": "BUY", "instrument_id": "EQ_1", "quantity": "1"}],
            request_hash="proposal_hash_skip_missing_notional",
        )

    assert result.status == "READY"
    assert result.intents == []

