from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.services.query_service.app.advisory_simulation.models import (
    CashFlowIntent,
    EngineOptions,
    FxSpotIntent,
    GroupConstraint,
    IntentRationale,
    LineageData,
    MarketDataSnapshot,
    Money,
    PortfolioSnapshot,
    Position,
    ProposalResult,
    ProposalSimulateRequest,
    ProposedCashFlow,
    ProposedTrade,
    Reconciliation,
    RuleResult,
    ShelfEntry,
    SimulatedState,
)


def test_advisory_engine_options_defaults():
    options = EngineOptions()
    assert options.enable_proposal_simulation is False
    assert options.enable_workflow_gates is True
    assert options.workflow_requires_client_consent is False
    assert options.client_consent_already_obtained is False
    assert options.proposal_apply_cash_flows_first is True
    assert options.proposal_block_negative_cash is True
    assert options.enable_drift_analytics is True
    assert options.enable_suitability_scanner is True
    assert options.enable_instrument_drift is True
    assert options.drift_top_contributors_limit == 5
    assert options.drift_unmodeled_exposure_threshold == Decimal("0.01")
    assert options.suitability_thresholds.single_position_max_weight == Decimal("0.10")
    assert options.suitability_thresholds.issuer_max_weight == Decimal("0.20")
    assert options.suitability_thresholds.cash_band_min_weight == Decimal("0.01")
    assert options.suitability_thresholds.cash_band_max_weight == Decimal("0.05")
    assert options.auto_funding is True
    assert options.funding_mode == "AUTO_FX"
    assert options.fx_funding_source_currency == "ANY_CASH"
    assert options.fx_generation_policy == "ONE_FX_PER_CCY"


def test_advisory_proposed_trade_requires_quantity_or_notional():
    with pytest.raises(ValidationError):
        ProposedTrade(side="BUY", instrument_id="EQ_1")


def test_advisory_proposed_trade_rejects_quantity_and_notional_together():
    with pytest.raises(ValidationError):
        ProposedTrade(
            side="BUY",
            instrument_id="EQ_1",
            quantity=Decimal("1"),
            notional={"amount": "100", "currency": "USD"},
        )


def test_advisory_proposed_trade_rejects_float_quantity():
    with pytest.raises(ValidationError):
        ProposedTrade(side="BUY", instrument_id="EQ_1", quantity=1.25)


def test_advisory_proposed_cash_flow_rejects_float_amount():
    with pytest.raises(ValidationError):
        ProposedCashFlow(currency="USD", amount=10.5)


def test_advisory_proposal_request_shape():
    request = ProposalSimulateRequest(
        portfolio_snapshot=PortfolioSnapshot(portfolio_id="pf", base_currency="USD"),
        market_data_snapshot=MarketDataSnapshot(prices=[], fx_rates=[]),
        shelf_entries=[ShelfEntry(instrument_id="EQ_1", status="APPROVED")],
        reference_model={
            "model_id": "mdl_1",
            "as_of": "2026-02-18",
            "base_currency": "USD",
            "asset_class_targets": [{"asset_class": "CASH", "weight": "1.0"}],
        },
        proposed_cash_flows=[ProposedCashFlow(currency="USD", amount=Decimal("100"))],
        proposed_trades=[ProposedTrade(side="BUY", instrument_id="EQ_1", quantity=Decimal("1"))],
    )
    assert request.proposed_cash_flows[0].intent_type == "CASH_FLOW"
    assert request.proposed_trades[0].intent_type == "SECURITY_TRADE"
    assert request.reference_model.model_id == "mdl_1"


def test_advisory_simulate_request_accepts_minimal_execution_shape():
    request = ProposalSimulateRequest.model_validate(
        {
            "portfolio_snapshot": {"portfolio_id": "pf", "base_currency": "USD"},
            "market_data_snapshot": {"prices": [], "fx_rates": []},
            "shelf_entries": [],
            "options": {"enable_proposal_simulation": True},
            "proposed_cash_flows": [],
            "proposed_trades": [],
        }
    )

    assert request.portfolio_snapshot.portfolio_id == "pf"
    assert request.options.enable_proposal_simulation is True


def test_advisory_proposal_result_accepts_fx_spot_intents():
    state = SimulatedState(
        total_value=Money(amount=Decimal("1000"), currency="USD"),
        cash_balances=[],
        positions=[],
        allocation_by_asset_class=[],
        allocation_by_instrument=[],
        allocation=[],
        allocation_by_attribute={},
    )
    result = ProposalResult(
        proposal_run_id="pr_test",
        correlation_id="corr_test",
        status="READY",
        before=state,
        intents=[
            CashFlowIntent(intent_id="oi_cf_1", currency="USD", amount=Decimal("10")),
            FxSpotIntent(
                intent_id="oi_fx_1",
                pair="EUR/USD",
                buy_currency="EUR",
                buy_amount=Decimal("100"),
                sell_currency="USD",
                sell_amount_estimated=Decimal("110"),
                rationale=IntentRationale(code="FUNDING", message="Fund EUR buys"),
            ),
        ],
        after_simulated=state,
        reconciliation=Reconciliation(
            before_total_value=Money(amount=Decimal("1000"), currency="USD"),
            after_total_value=Money(amount=Decimal("1000"), currency="USD"),
            delta=Money(amount=Decimal("0"), currency="USD"),
            tolerance=Money(amount=Decimal("1"), currency="USD"),
            status="OK",
        ),
        rule_results=[
            RuleResult(
                rule_id="DATA_QUALITY",
                severity="HARD",
                status="PASS",
                measured=Decimal("0"),
                threshold={"max": Decimal("0")},
                reason_code="OK",
            )
        ],
        explanation={"summary": "READY"},
        diagnostics={"data_quality": {"price_missing": [], "fx_missing": [], "shelf_missing": []}},
        lineage=LineageData(
            portfolio_snapshot_id="pf",
            market_data_snapshot_id="md",
            request_hash="hash",
        ),
    )

    assert result.intents[1].intent_type == "FX_SPOT"


def test_snapshot_models_accept_snapshot_id() -> None:
    portfolio = PortfolioSnapshot(snapshot_id="ps_1", portfolio_id="pf", base_currency="USD")
    market = MarketDataSnapshot(
        snapshot_id="md_1",
        prices=[],
        fx_rates=[],
    )

    assert portfolio.snapshot_id == "ps_1"
    assert market.snapshot_id == "md_1"


def test_suitability_thresholds_validate_liquidity_tier_keys() -> None:
    with pytest.raises(ValidationError):
        EngineOptions(suitability_thresholds={"max_weight_by_liquidity_tier": {"L9": "0.10"}})


def test_suitability_thresholds_validate_cash_band_order() -> None:
    with pytest.raises(ValidationError):
        EngineOptions(
            suitability_thresholds={
                "cash_band_min_weight": "0.10",
                "cash_band_max_weight": "0.05",
            }
        )


def test_suitability_thresholds_validate_liquidity_tier_values() -> None:
    with pytest.raises(ValidationError):
        EngineOptions(suitability_thresholds={"max_weight_by_liquidity_tier": {"L4": "1.01"}})


def test_proposed_trade_notional_validators_reject_float_and_non_positive() -> None:
    with pytest.raises(ValidationError):
        ProposedTrade.model_validate(
            {
                "side": "BUY",
                "instrument_id": "EQ_1",
                "notional": {"amount": 10.5, "currency": "USD"},
            }
        )

    with pytest.raises(ValidationError):
        ProposedTrade.model_validate(
            {
                "side": "BUY",
                "instrument_id": "EQ_1",
                "notional": {"amount": "0", "currency": "USD"},
            }
        )


def test_position_rejects_tax_lots_that_do_not_sum_to_quantity() -> None:
    with pytest.raises(ValidationError, match="sum\\(lot.quantity\\)"):
        Position.model_validate(
            {
                "instrument_id": "EQ_1",
                "quantity": "5",
                "lots": [
                    {
                        "lot_id": "lot_1",
                        "quantity": "2",
                        "unit_cost": {"amount": "100", "currency": "USD"},
                        "purchase_date": "2025-01-01",
                    },
                    {
                        "lot_id": "lot_2",
                        "quantity": "2",
                        "unit_cost": {"amount": "90", "currency": "USD"},
                        "purchase_date": "2025-01-02",
                    },
                ],
            }
        )


def test_group_constraint_validators_reject_invalid_keys_and_weights() -> None:
    with pytest.raises(ValidationError, match="group_constraints keys must use format"):
        EngineOptions(group_constraints={"sector": {"max_weight": "0.25"}})

    with pytest.raises(ValidationError, match="group_constraints keys must use format"):
        EngineOptions(group_constraints={":TECH": {"max_weight": "0.25"}})

    with pytest.raises(ValidationError, match="max_weight must be between 0 and 1 inclusive"):
        GroupConstraint(max_weight=Decimal("1.5"))


def test_engine_options_reject_invalid_turnover_and_overdraft_values() -> None:
    with pytest.raises(ValidationError, match="max_turnover_pct must be between 0 and 1 inclusive"):
        EngineOptions(max_turnover_pct=Decimal("1.1"))

    with pytest.raises(ValidationError, match="keys must be non-empty currency codes"):
        EngineOptions(max_overdraft_by_ccy={"": Decimal("1")})

    with pytest.raises(ValidationError, match="values must be non-negative"):
        EngineOptions(max_overdraft_by_ccy={"USD": Decimal("-1")})

