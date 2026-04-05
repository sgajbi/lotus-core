from decimal import Decimal

from src.services.query_service.app.advisory_simulation.compliance import RuleEngine
from src.services.query_service.app.advisory_simulation.models import (
    DiagnosticsData,
    EngineOptions,
    Money,
    SuppressedIntent,
)
from src.services.query_service.app.advisory_simulation.valuation import build_simulated_state
from tests.shared.factories import cash, portfolio_snapshot, position, shelf_entry


def _build_state():
    portfolio = portfolio_snapshot(
        positions=[position("EQ_1", "10"), position("EQ_2", "2")],
        cash_balances=[cash("USD", "10")],
    )
    market_data = build_market_data()
    shelf = [shelf_entry("EQ_1", asset_class="EQUITY"), shelf_entry("EQ_2", asset_class="EQUITY")]
    dq_log = {"price_missing": [], "fx_missing": [], "shelf_missing": []}
    warnings: list[str] = []
    state = build_simulated_state(portfolio, market_data, shelf, dq_log, warnings)
    return state, DiagnosticsData(data_quality=dq_log, warnings=warnings)


def build_market_data():
    from tests.shared.factories import market_data_snapshot, price

    return market_data_snapshot(
        prices=[price("EQ_1", "100", "USD"), price("EQ_2", "50", "USD")],
        fx_rates=[],
    )


def test_rule_engine_emits_pass_results_for_clean_portfolio() -> None:
    state, diagnostics = _build_state()
    options = EngineOptions(
        cash_band_min_weight=Decimal("0"),
        cash_band_max_weight=Decimal("1"),
        single_position_max_weight=Decimal("0.90"),
    )

    results = RuleEngine.evaluate(state, options, diagnostics)

    assert {result.rule_id for result in results} == {
        "CASH_BAND",
        "SINGLE_POSITION_MAX",
        "DATA_QUALITY",
        "MIN_TRADE_SIZE",
        "NO_SHORTING",
        "INSUFFICIENT_CASH",
    }
    assert all(result.status == "PASS" for result in results)


def test_rule_engine_blocks_cash_band_single_position_and_data_quality() -> None:
    state, diagnostics = _build_state()
    diagnostics = diagnostics.model_copy(
        update={
            "data_quality": {
                "price_missing": ["EQ_9"],
                "fx_missing": ["EUR/USD"],
                "shelf_missing": ["EQ_8"],
            },
            "suppressed_intents": [
                SuppressedIntent(
                    instrument_id="EQ_1",
                    reason="BELOW_MIN_TRADE_SIZE",
                    intended_notional=Money(amount=Decimal("5"), currency="USD"),
                    threshold=Money(amount=Decimal("10"), currency="USD"),
                )
            ],
        }
    )
    options = EngineOptions(
        cash_band_min_weight=Decimal("0.20"),
        cash_band_max_weight=Decimal("0.25"),
        single_position_max_weight=Decimal("0.50"),
        block_on_missing_prices=True,
        block_on_missing_fx=True,
    )

    results = RuleEngine.evaluate(state, options, diagnostics)

    by_rule = {result.rule_id: result for result in results}
    assert by_rule["CASH_BAND"].status == "FAIL"
    assert by_rule["SINGLE_POSITION_MAX"].status == "FAIL"
    assert by_rule["DATA_QUALITY"].measured == Decimal("3")
    assert by_rule["MIN_TRADE_SIZE"].reason_code == "INTENTS_SUPPRESSED"


def test_rule_engine_ignores_price_and_fx_when_blocking_disabled() -> None:
    state, diagnostics = _build_state()
    diagnostics = diagnostics.model_copy(
        update={
            "data_quality": {
                "price_missing": ["EQ_9"],
                "fx_missing": ["EUR/USD"],
                "shelf_missing": [],
            }
        }
    )

    results = RuleEngine.evaluate(
        state,
        EngineOptions(block_on_missing_prices=False, block_on_missing_fx=False),
        diagnostics,
    )

    assert next(result for result in results if result.rule_id == "DATA_QUALITY").status == "PASS"


def test_rule_engine_detects_shorting_and_negative_cash() -> None:
    state, diagnostics = _build_state()
    state.positions[0].quantity = Decimal("-1")
    state.cash_balances[0].amount = Decimal("-5")

    results = RuleEngine.evaluate(state, EngineOptions(), diagnostics)

    by_rule = {result.rule_id: result for result in results}
    assert by_rule["NO_SHORTING"].status == "FAIL"
    assert by_rule["INSUFFICIENT_CASH"].status == "FAIL"


def test_rule_engine_marks_single_position_no_limit_when_unconfigured() -> None:
    state, diagnostics = _build_state()
    options = EngineOptions(single_position_max_weight=None)

    results = RuleEngine.evaluate(state, options, diagnostics)

    single_position = next(result for result in results if result.rule_id == "SINGLE_POSITION_MAX")
    assert single_position.status == "PASS"
    assert single_position.reason_code == "NO_LIMIT_SET"
