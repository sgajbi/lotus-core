"""Verify canonical cost-basis calculation policy across transaction families."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from portfolio_common.domain.transaction.type_registry import (
    PRODUCTION_BOOKING_TRANSACTION_TYPES,
    TRANSACTION_TYPE_REGISTRY,
)

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostBasisStrategy,
    CostBasisCalculator,
    CostBasisTransaction,
    CostCalculationErrorCollector,
    Fees,
    FIFOBasisStrategy,
    LotBasisTransferResult,
    LotDispositionEngine,
    LotRestatement,
    SourceLotBasisTransferAllocation,
    has_governed_transaction_cost_authority,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis.calculation import (  # noqa: E501
    cost_basis_calculator as calculator_module,
)


@pytest.fixture
def mock_disposition_engine():
    mock = MagicMock(spec=LotDispositionEngine)
    mock.get_available_quantity.return_value = Decimal("1000000")
    return mock


@pytest.fixture
def error_reporter():
    return CostCalculationErrorCollector()


@pytest.fixture
def cost_calculator(mock_disposition_engine, error_reporter):
    return CostBasisCalculator(
        disposition_engine=mock_disposition_engine, error_reporter=error_reporter
    )


class _StringCountedAmount:
    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


def _canonical_fx_transaction(
    *,
    transaction_id: str = "FX-BASELINE-001",
    transaction_type: str = "FX_FORWARD",
    component_type: str = "FX_CONTRACT_CLOSE",
    fx_realized_pnl_mode: str = "NONE",
    **updates,
) -> CostBasisTransaction:
    data = {
        "transaction_id": transaction_id,
        "portfolio_id": "PORT-FX",
        "instrument_id": "FXC-EURUSD-001",
        "security_id": "FXC-EURUSD-001",
        "transaction_type": transaction_type,
        "transaction_date": datetime(2026, 7, 1, 9, 0, 0),
        "settlement_date": datetime(2026, 7, 1, 9, 0, 0),
        "quantity": Decimal("0"),
        "price": Decimal("0"),
        "gross_transaction_amount": Decimal("0"),
        "trade_currency": "USD",
        "currency": "USD",
        "portfolio_base_currency": "USD",
        "transaction_fx_rate": Decimal("1"),
        "component_type": component_type,
        "component_id": f"{transaction_id}-COMP",
        "linked_component_ids": [f"{transaction_id}-BUY", f"{transaction_id}-SELL"],
        "pair_base_currency": "EUR",
        "pair_quote_currency": "USD",
        "fx_rate_quote_convention": "QUOTE_PER_BASE",
        "buy_currency": "USD",
        "sell_currency": "EUR",
        "buy_amount": Decimal("1095000"),
        "sell_amount": Decimal("1000000"),
        "contract_rate": Decimal("1.095"),
        "fx_contract_id": "FXC-2026-0001",
        "fx_contract_open_transaction_id": "FX-OPEN-001",
        "spot_exposure_model": "NONE",
        "fx_realized_pnl_mode": fx_realized_pnl_mode,
    }
    data.update(updates)
    return CostBasisTransaction(**data)


@pytest.fixture
def buy_transaction():
    return CostBasisTransaction(
        transaction_id="BUY001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        settlement_date=datetime(2023, 1, 3),
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("1500"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("5.5")),
        accrued_interest=Decimal("10.0"),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )


@pytest.fixture
def sell_transaction():
    return CostBasisTransaction(
        transaction_id="SELL001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="SELL",
        transaction_date=datetime(2023, 1, 10),
        settlement_date=datetime(2023, 1, 12),
        quantity=Decimal("5"),
        gross_transaction_amount=Decimal("800"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("3.0")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )


def test_buy_strategy(cost_calculator, mock_disposition_engine, buy_transaction):
    cost_calculator.calculate_transaction_costs(buy_transaction)
    assert buy_transaction.net_cost_local == Decimal("1515.5")
    assert buy_transaction.net_cost == Decimal("1515.5")
    assert buy_transaction.gross_cost == Decimal("1500")
    assert buy_transaction.realized_gain_loss == Decimal("0")
    assert buy_transaction.realized_gain_loss_local == Decimal("0")
    lineage = buy_transaction.calculation_lineage
    assert lineage.algorithm_id == "transaction-cost-basis-calculation"
    assert lineage.numeric_output_policy is not None
    assert lineage.numeric_output_policy.policy_id == "transaction-cost-ledger-output@1.0.0"
    mock_disposition_engine.add_buy_lot.assert_called_once_with(buy_transaction)


def test_transaction_cost_lineage_is_deterministic_and_material_input_sensitive(
    cost_calculator,
) -> None:
    def transaction(fee: str) -> CostBasisTransaction:
        return CostBasisTransaction(
            transaction_id="BUY-LINEAGE-001",
            portfolio_id="P1",
            instrument_id="AAPL",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2026, 8, 1),
            quantity=Decimal("10"),
            gross_transaction_amount=Decimal("1500"),
            trade_currency="USD",
            fees=Fees(brokerage=Decimal(fee)),
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal("1"),
        )

    baseline = transaction("5.5")
    repeated = transaction("5.5")
    changed = transaction("6.5")

    cost_calculator.calculate_transaction_costs(baseline)
    cost_calculator.calculate_transaction_costs(repeated)
    cost_calculator.calculate_transaction_costs(changed)
    replayed = CostBasisTransaction(
        **baseline.model_dump(exclude={"calculation_lineage", "error_reason"})
    )
    cost_calculator.calculate_transaction_costs(replayed)

    assert baseline.calculation_lineage == repeated.calculation_lineage
    assert replayed.calculation_lineage == baseline.calculation_lineage
    assert baseline.calculation_lineage.input_content_hash != (
        changed.calculation_lineage.input_content_hash
    )
    assert baseline.calculation_lineage.output_content_hash != (
        changed.calculation_lineage.output_content_hash
    )


def test_transaction_cost_authority_requires_current_input_and_output_bound_lineage(
    cost_calculator,
    buy_transaction,
) -> None:
    cost_calculator.calculate_transaction_costs(buy_transaction)
    payload = buy_transaction.model_dump()
    lineage = buy_transaction.calculation_lineage

    assert has_governed_transaction_cost_authority(payload)
    assert has_governed_transaction_cost_authority({**payload, "tenant_id": "tenant-a"})
    assert not has_governed_transaction_cost_authority({**payload, "net_cost": None})
    assert not has_governed_transaction_cost_authority({**payload, "net_cost_local": None})
    assert not has_governed_transaction_cost_authority({**payload, "calculation_lineage": None})
    assert not has_governed_transaction_cost_authority(
        {
            **payload,
            "calculation_lineage": replace(lineage, algorithm_id="foreign-calculation"),
        }
    )
    assert not has_governed_transaction_cost_authority(
        {
            **payload,
            "calculation_lineage": replace(lineage, algorithm_version=1),
        }
    )
    assert not has_governed_transaction_cost_authority(
        {**payload, "net_cost": payload["net_cost"] + Decimal("1")}
    )
    assert not has_governed_transaction_cost_authority(
        {**payload, "quantity": payload["quantity"] + Decimal("1")}
    )
    assert not has_governed_transaction_cost_authority(
        {
            **payload,
            "gross_transaction_amount": payload["gross_transaction_amount"] + Decimal("1"),
        }
    )
    assert not has_governed_transaction_cost_authority(
        {**payload, "product_type": "BOND", "asset_class": "Fixed Income"}
    )
    assert not has_governed_transaction_cost_authority(
        {
            **payload,
            "fees": {**payload["fees"], "stamp_duty": Decimal("1")},
        }
    )


def test_transaction_cost_lineage_is_stable_across_database_decimal_scale(
    cost_calculator,
) -> None:
    def transaction(decimal_scale: str) -> CostBasisTransaction:
        return CostBasisTransaction(
            transaction_id="BUY-LINEAGE-SCALE-001",
            portfolio_id="P1",
            instrument_id="AAPL",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2026, 8, 1),
            quantity=Decimal(f"10{decimal_scale}"),
            gross_transaction_amount=Decimal(f"1500{decimal_scale}"),
            trade_currency="USD",
            fees=Fees(brokerage=Decimal(f"5{decimal_scale}")),
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal(f"1{decimal_scale}"),
        )

    source_event = transaction("")
    database_round_trip = transaction(".0000000000")

    cost_calculator.calculate_transaction_costs(source_event)
    cost_calculator.calculate_transaction_costs(database_round_trip)

    assert source_event.calculation_lineage == database_round_trip.calculation_lineage
    assert source_event.calculation_lineage.algorithm_version == 2


def test_transaction_cost_lineage_ignores_redundant_trade_fee_scale(
    cost_calculator,
) -> None:
    def transaction(*, brokerage: str, trade_fee: str) -> CostBasisTransaction:
        return CostBasisTransaction(
            transaction_id="BUY-LINEAGE-NAMED-FEE-001",
            portfolio_id="P1",
            instrument_id="AAPL",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2026, 8, 1),
            quantity=Decimal("10"),
            gross_transaction_amount=Decimal("1500"),
            trade_currency="USD",
            fees=Fees(brokerage=Decimal(brokerage)),
            trade_fee=trade_fee,
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal("1"),
        )

    source_event = transaction(brokerage="2.00", trade_fee="2.00")
    database_round_trip = transaction(
        brokerage="2.0000000000",
        trade_fee="2.0000000000",
    )
    changed_fee = transaction(brokerage="2.01", trade_fee="2.01")

    cost_calculator.calculate_transaction_costs(source_event)
    cost_calculator.calculate_transaction_costs(database_round_trip)
    cost_calculator.calculate_transaction_costs(changed_fee)

    assert source_event.calculation_lineage == database_round_trip.calculation_lineage
    assert source_event.calculation_lineage.input_content_hash != (
        changed_fee.calculation_lineage.input_content_hash
    )


def test_transaction_cost_lineage_excludes_settlement_owned_generated_linkage(
    cost_calculator,
) -> None:
    source = {
        "transaction_id": "BUY-LINEAGE-SETTLEMENT-001",
        "portfolio_id": "P1",
        "instrument_id": "AAPL",
        "security_id": "S1",
        "transaction_type": "BUY",
        "transaction_date": datetime(2026, 8, 1),
        "quantity": Decimal("10"),
        "gross_transaction_amount": Decimal("1500"),
        "trade_currency": "USD",
        "portfolio_base_currency": "USD",
        "transaction_fx_rate": Decimal("1"),
    }
    before_settlement = CostBasisTransaction(**source)
    after_settlement = CostBasisTransaction(
        **source,
        created_at=datetime(2026, 8, 1, 1, 2, 3),
        economic_event_id="ECON-BUY-LINEAGE-SETTLEMENT-001",
        epoch=42,
        linked_transaction_group_id="GROUP-BUY-LINEAGE-SETTLEMENT-001",
        external_cash_transaction_id="BUY-LINEAGE-SETTLEMENT-001-CASHLEG",
    )

    cost_calculator.calculate_transaction_costs(before_settlement)
    cost_calculator.calculate_transaction_costs(after_settlement)

    assert before_settlement.calculation_lineage == after_settlement.calculation_lineage


@pytest.mark.parametrize(
    "changed_field",
    [
        "allocated_cost_basis_local",
        "allocated_cost_basis_base",
        "realized_capital_pnl_local",
        "realized_fx_pnl_local",
        "realized_total_pnl_local",
        "realized_capital_pnl_base",
        "realized_fx_pnl_base",
        "realized_total_pnl_base",
    ],
)
def test_transaction_cost_lineage_output_covers_persisted_pnl_decomposition(
    cost_calculator,
    changed_field: str,
) -> None:
    def transaction() -> CostBasisTransaction:
        return CostBasisTransaction(
            transaction_id="BUY-DECOMPOSITION-LINEAGE-001",
            portfolio_id="P1",
            instrument_id="AAPL",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=datetime(2026, 8, 1),
            quantity=Decimal("10"),
            gross_transaction_amount=Decimal("1500"),
            trade_currency="USD",
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal("1"),
        )

    baseline_components = {
        "allocated_cost_basis_local": Decimal("1200"),
        "allocated_cost_basis_base": Decimal("1210"),
        "realized_capital_pnl_local": Decimal("200"),
        "realized_fx_pnl_local": Decimal("10"),
        "realized_total_pnl_local": Decimal("210"),
        "realized_capital_pnl_base": Decimal("205"),
        "realized_fx_pnl_base": Decimal("12"),
        "realized_total_pnl_base": Decimal("217"),
    }
    changed_components = dict(baseline_components)
    changed_components[changed_field] += Decimal("1")
    component_outputs = iter((baseline_components, changed_components))

    strategy = MagicMock()

    def calculate_costs(calculated_transaction, *_args) -> None:
        calculated_transaction.gross_cost = Decimal("1500")
        calculated_transaction.net_cost = Decimal("1510")
        calculated_transaction.net_cost_local = Decimal("1510")
        calculated_transaction.realized_gain_loss = Decimal("217")
        calculated_transaction.realized_gain_loss_local = Decimal("210")
        for field_name, value in next(component_outputs).items():
            calculated_transaction.set_calculated_field(field_name, value)

    strategy.calculate_costs.side_effect = calculate_costs
    cost_calculator._strategies["BUY"] = strategy
    baseline = transaction()
    changed = transaction()

    cost_calculator.calculate_transaction_costs(baseline)
    cost_calculator.calculate_transaction_costs(changed)

    baseline_lineage = baseline.calculation_lineage
    changed_lineage = changed.calculation_lineage
    assert baseline_lineage is not None
    assert changed_lineage is not None
    assert baseline_lineage.input_content_hash == changed_lineage.input_content_hash
    assert (
        baseline.gross_cost,
        baseline.net_cost,
        baseline.net_cost_local,
        baseline.realized_gain_loss,
        baseline.realized_gain_loss_local,
    ) == (
        changed.gross_cost,
        changed.net_cost,
        changed.net_cost_local,
        changed.realized_gain_loss,
        changed.realized_gain_loss_local,
    )
    assert baseline_lineage.output_content_hash != changed_lineage.output_content_hash


def test_transaction_cost_lineage_replay_excludes_stale_decomposition_outputs(
    cost_calculator,
) -> None:
    source = {
        "transaction_id": "BUY-DECOMPOSITION-REPLAY-001",
        "portfolio_id": "P1",
        "instrument_id": "AAPL",
        "security_id": "AAPL",
        "transaction_type": "BUY",
        "transaction_date": datetime(2026, 1, 1),
        "quantity": Decimal("10"),
        "gross_transaction_amount": Decimal("1500"),
        "trade_currency": "USD",
        "portfolio_base_currency": "USD",
        "transaction_fx_rate": Decimal("1"),
    }
    calculated_outputs = {
        "allocated_cost_basis_base": Decimal("1210"),
        "allocated_cost_basis_local": Decimal("1200"),
        "realized_capital_pnl_base": Decimal("205"),
        "realized_capital_pnl_local": Decimal("200"),
        "realized_fx_pnl_base": Decimal("12"),
        "realized_fx_pnl_local": Decimal("10"),
        "realized_total_pnl_base": Decimal("217"),
        "realized_total_pnl_local": Decimal("210"),
    }
    fresh = CostBasisTransaction(**source)
    replay = CostBasisTransaction(**source, **calculated_outputs)
    strategy = MagicMock()

    def calculate_costs(transaction, *_args) -> None:
        transaction.gross_cost = Decimal("1500")
        transaction.net_cost = Decimal("1510")
        transaction.net_cost_local = Decimal("1510")
        transaction.realized_gain_loss = Decimal("217")
        transaction.realized_gain_loss_local = Decimal("210")
        for field_name, value in calculated_outputs.items():
            transaction.set_calculated_field(field_name, value)

    strategy.calculate_costs.side_effect = calculate_costs
    cost_calculator._strategies["BUY"] = strategy

    cost_calculator.calculate_transaction_costs(fresh)
    cost_calculator.calculate_transaction_costs(replay)

    assert fresh.calculation_lineage is not None
    assert replay.calculation_lineage is not None
    assert (
        fresh.calculation_lineage.input_content_hash
        == replay.calculation_lineage.input_content_hash
    )
    assert (
        fresh.calculation_lineage.output_content_hash
        == replay.calculation_lineage.output_content_hash
    )


def test_buy_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    dual_currency_buy = CostBasisTransaction(
        transaction_id="DC_BUY_01",
        portfolio_id="P_USD",
        instrument_id="AIR.lotus-performance",
        security_id="S_AIR",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("15000"),
        trade_currency="EUR",
        fees=Fees(brokerage=Decimal("10")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.15"),
    )
    cost_calculator.calculate_transaction_costs(dual_currency_buy)
    assert dual_currency_buy.net_cost_local == Decimal("15010")
    assert dual_currency_buy.net_cost == Decimal("17261.50")
    assert dual_currency_buy.gross_cost == Decimal("17250.00")
    assert dual_currency_buy.realized_gain_loss == Decimal("0")
    assert dual_currency_buy.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(dual_currency_buy)


def test_buy_strategy_normalizes_cross_currency_calculated_costs(
    cost_calculator,
    mock_disposition_engine,
) -> None:
    transaction = CostBasisTransaction(
        transaction_id="BUY_PRECISION_01",
        portfolio_id="P_USD",
        instrument_id="SEC_EUR",
        security_id="SEC_EUR",
        transaction_type="BUY",
        transaction_date=datetime(2026, 7, 28),
        quantity=Decimal("1"),
        gross_transaction_amount=Decimal("1.0000000001"),
        trade_currency="EUR",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0000000001"),
    )

    cost_calculator.calculate_transaction_costs(transaction)

    assert transaction.gross_cost == Decimal("1.0000000002")
    assert transaction.net_cost_local == Decimal("1.0000000001")
    assert transaction.net_cost == Decimal("1.0000000002")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(transaction)


def test_cost_calculator_normalizes_same_currency_codes_before_fx_requirement(
    cost_calculator, mock_disposition_engine
):
    same_currency_buy = CostBasisTransaction(
        transaction_id="BUY_SAME_CCY_NORMALIZE_01",
        portfolio_id="P_USD",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency=" usd ",
        portfolio_base_currency="USD",
        transaction_fx_rate=None,
    )

    cost_calculator.calculate_transaction_costs(same_currency_buy)

    assert same_currency_buy.trade_currency == "USD"
    assert same_currency_buy.portfolio_base_currency == "USD"
    assert same_currency_buy.transaction_fx_rate == Decimal("1")
    assert same_currency_buy.net_cost == Decimal("1000")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(same_currency_buy)


def test_cost_calculator_rejects_cross_currency_booking_without_fx_rate(
    cost_calculator, mock_disposition_engine, error_reporter
) -> None:
    cross_currency_buy = CostBasisTransaction(
        transaction_id="BUY_MISSING_CROSS_CURRENCY_FX_01",
        portfolio_id="P_SGD",
        instrument_id="BOND_EUR_01",
        security_id="BOND_EUR_01",
        transaction_type="BUY",
        transaction_date=datetime(2026, 7, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="EUR",
        portfolio_base_currency="SGD",
        transaction_fx_rate=None,
    )

    cost_calculator.calculate_transaction_costs(cross_currency_buy)

    errors = error_reporter.get_errors()
    assert errors[0].error_reason == (
        "Missing/invalid FX rate for cross-currency transaction from EUR to SGD."
    )
    assert cross_currency_buy.net_cost is None
    assert cross_currency_buy.net_cost_local is None
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_cost_calculator_rejects_non_positive_same_currency_fx_rate(
    cost_calculator, mock_disposition_engine, error_reporter
):
    same_currency_buy = CostBasisTransaction(
        transaction_id="BUY_SAME_CCY_NEGATIVE_FX_01",
        portfolio_id="P_USD",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    same_currency_buy.transaction_fx_rate = Decimal("-1.0")

    cost_calculator.calculate_transaction_costs(same_currency_buy)

    assert error_reporter.has_errors_for("BUY_SAME_CCY_NEGATIVE_FX_01")
    assert same_currency_buy.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_cost_calculator_reports_invalid_fx_rate_text(
    cost_calculator, mock_disposition_engine, error_reporter
):
    same_currency_buy = CostBasisTransaction(
        transaction_id="BUY_INVALID_FX_TEXT_01",
        portfolio_id="P_USD",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    same_currency_buy.transaction_fx_rate = "not-a-number"

    cost_calculator.calculate_transaction_costs(same_currency_buy)

    assert error_reporter.has_errors_for("BUY_INVALID_FX_TEXT_01")
    assert "invalid decimal for transaction_fx_rate" in error_reporter.get_errors()[0].error_reason
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_cost_calculator_normalizes_transaction_type_before_strategy_resolution(
    cost_calculator, mock_disposition_engine
):
    lowercase_buy = CostBasisTransaction(
        transaction_id="BUY_LOWERCASE_TYPE_01",
        portfolio_id="P_USD",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type=" buy ",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(lowercase_buy)

    assert lowercase_buy.transaction_type == "BUY"
    assert lowercase_buy.net_cost == Decimal("1000.0")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(lowercase_buy)


def test_cost_calculator_has_explicit_strategies_for_production_booking_types(
    cost_calculator,
):
    cash_account_types = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.settlement_behavior == "cash_account_required"
    }

    assert set(cost_calculator._strategies) | cash_account_types == (
        PRODUCTION_BOOKING_TRANSACTION_TYPES
    )
    assert set(cost_calculator._strategies).isdisjoint(cash_account_types)
    assert "OTHER" not in cost_calculator._strategies


def _cash_consideration(**overrides: object) -> CostBasisTransaction:
    values = {
        "transaction_id": "CA-CASH-CONSIDERATION-001",
        "portfolio_id": "P1",
        "instrument_id": "SOURCE-SECURITY",
        "security_id": "SOURCE-SECURITY",
        "transaction_type": "CASH_CONSIDERATION",
        "transaction_date": datetime(2026, 5, 3),
        "quantity": Decimal("0"),
        "price": Decimal("0"),
        "gross_transaction_amount": Decimal("250"),
        "trade_currency": "USD",
        "portfolio_base_currency": "USD",
        "transaction_fx_rate": Decimal("1"),
        "allocated_cost_basis_local": Decimal("50"),
        "allocated_cost_basis_base": Decimal("50"),
    }
    values.update(overrides)
    return CostBasisTransaction(**values)


def _cash_in_lieu(**overrides: object) -> CostBasisTransaction:
    values = {
        "transaction_id": "CA-CASH-IN-LIEU-001",
        "portfolio_id": "P1",
        "instrument_id": "TARGET-SECURITY",
        "security_id": "TARGET-SECURITY",
        "transaction_type": "CASH_IN_LIEU",
        "transaction_date": datetime(2026, 5, 3),
        "quantity": Decimal("0.5"),
        "price": Decimal("120"),
        "gross_transaction_amount": Decimal("60"),
        "trade_currency": "USD",
        "portfolio_base_currency": "SGD",
        "transaction_fx_rate": Decimal("1.35"),
        "allocated_cost_basis_local": Decimal("50"),
        "allocated_cost_basis_base": Decimal("67.5"),
        "realized_capital_pnl_local": Decimal("10"),
        "realized_fx_pnl_local": Decimal("0"),
        "realized_capital_pnl_base": Decimal("10"),
        "realized_fx_pnl_base": Decimal("3.5"),
    }
    values.update(overrides)
    return CostBasisTransaction(**values)


def test_cash_in_lieu_reconciles_fractional_basis_and_cross_currency_pnl_components(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
) -> None:
    transaction = _cash_in_lieu()
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("67.5"),
        Decimal("50"),
        Decimal("0.5"),
        None,
    )

    cost_calculator.calculate_transaction_costs(transaction)

    assert not error_reporter.has_errors_for(transaction.transaction_id)
    assert transaction.net_cost_local == Decimal("-50")
    assert transaction.net_cost == Decimal("-67.5")
    assert transaction.realized_gain_loss_local == Decimal("10")
    assert transaction.realized_gain_loss == Decimal("13.50")
    assert transaction.realized_capital_pnl_local == Decimal("10")
    assert transaction.realized_fx_pnl_local == Decimal("0")
    assert transaction.realized_total_pnl_local == Decimal("10")
    assert transaction.realized_capital_pnl_base == Decimal("10")
    assert transaction.realized_fx_pnl_base == Decimal("3.5")
    assert transaction.realized_total_pnl_base == Decimal("13.50")
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(transaction)
    mock_disposition_engine.commit_disposal_record.assert_called_once_with(
        transaction.transaction_id
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"allocated_cost_basis_local": None}, "allocated_cost_basis_local is required"),
        ({"allocated_cost_basis_base": None}, "allocated_cost_basis_base is required"),
        ({"quantity": Decimal("0")}, "quantity_delta must be greater than 0"),
    ],
)
def test_cash_in_lieu_rejects_incomplete_fractional_disposal_before_consumption(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
    overrides: dict[str, object],
    message: str,
) -> None:
    transaction = _cash_in_lieu(**overrides)

    cost_calculator.calculate_transaction_costs(transaction)

    assert error_reporter.has_errors_for(transaction.transaction_id)
    assert message in error_reporter.get_errors()[0].error_reason
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_cash_in_lieu_rejects_consumed_basis_that_disagrees_with_allocated_basis(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
) -> None:
    transaction = _cash_in_lieu()
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("70"),
        Decimal("51"),
        Decimal("0.5"),
        None,
    )

    cost_calculator.calculate_transaction_costs(transaction)

    assert error_reporter.has_errors_for(transaction.transaction_id)
    assert "consumed local/base basis must equal allocated fractional basis" in (
        error_reporter.get_errors()[0].error_reason
    )
    mock_disposition_engine.commit_disposal_record.assert_not_called()
    mock_disposition_engine.discard_pending_disposal.assert_called_with(transaction.transaction_id)


@pytest.mark.parametrize(
    ("movement_direction", "expected_local", "expected_base"),
    [
        ("INFLOW", Decimal("60"), Decimal("81.00")),
        ("OUTFLOW", Decimal("-60"), Decimal("-81.00")),
    ],
)
def test_cross_currency_adjustment_uses_direction_aware_cash_basis(
    cost_calculator,
    error_reporter,
    movement_direction: str,
    expected_local: Decimal,
    expected_base: Decimal,
) -> None:
    transaction = CostBasisTransaction(
        transaction_id=f"ADJUSTMENT-{movement_direction}-01",
        portfolio_id="P1",
        instrument_id="CASH_EUR",
        security_id="CASH_EUR",
        transaction_type="ADJUSTMENT",
        transaction_date=datetime(2026, 5, 10),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("60"),
        trade_currency="EUR",
        portfolio_base_currency="SGD",
        transaction_fx_rate=Decimal("1.35"),
        movement_direction=movement_direction,
    )

    cost_calculator.calculate_transaction_costs(transaction)

    assert not error_reporter.has_errors_for(transaction.transaction_id)
    assert transaction.net_cost_local == expected_local
    assert transaction.net_cost == expected_base
    assert transaction.gross_cost == expected_base
    assert transaction.realized_gain_loss_local is None
    assert transaction.realized_gain_loss is None


def test_adjustment_rejects_non_domain_movement_direction(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
) -> None:
    transaction = CostBasisTransaction(
        transaction_id="ADJUSTMENT-INVALID-DIRECTION-01",
        portfolio_id="P1",
        instrument_id="CASH_EUR",
        security_id="CASH_EUR",
        transaction_type="ADJUSTMENT",
        transaction_date=datetime(2026, 5, 10),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("60"),
        trade_currency="EUR",
        portfolio_base_currency="SGD",
        transaction_fx_rate=Decimal("1.35"),
        movement_direction="REVERSAL",
    )

    cost_calculator.calculate_transaction_costs(transaction)

    errors = error_reporter.get_errors()
    assert errors[0].error_reason == (
        "ADJUSTMENT invariant violation: movement_direction must be INFLOW or OUTFLOW."
    )
    assert transaction.net_cost is None
    assert transaction.net_cost_local is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_cash_consideration_strategy_records_disposed_basis_and_realized_pnl(
    cost_calculator, mock_disposition_engine, error_reporter
) -> None:
    transaction = _cash_consideration()

    cost_calculator.calculate_transaction_costs(transaction)

    assert not error_reporter.has_errors_for(transaction.transaction_id)
    assert transaction.net_cost_local == Decimal("-50")
    assert transaction.net_cost == Decimal("-50")
    assert transaction.gross_cost == Decimal("-50")
    assert transaction.realized_gain_loss_local == Decimal("200")
    assert transaction.realized_gain_loss == Decimal("200")
    assert transaction.realized_capital_pnl_local == Decimal("200")
    assert transaction.realized_fx_pnl_local == Decimal("0")
    assert transaction.realized_total_pnl_local == Decimal("200")
    assert transaction.realized_capital_pnl_base == Decimal("200")
    assert transaction.realized_fx_pnl_base == Decimal("0")
    assert transaction.realized_total_pnl_base == Decimal("200")
    assert transaction.model_dump()["realized_total_pnl_base"] == Decimal("200")
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_cash_consideration_strategy_preserves_cross_currency_pnl_components(
    cost_calculator, error_reporter
) -> None:
    transaction = _cash_consideration(
        portfolio_base_currency="SGD",
        transaction_fx_rate=Decimal("1.4"),
        allocated_cost_basis_base=Decimal("60"),
        realized_capital_pnl_local=Decimal("190"),
        realized_fx_pnl_local=Decimal("10"),
        realized_capital_pnl_base=Decimal("270"),
        realized_fx_pnl_base=Decimal("20"),
    )

    cost_calculator.calculate_transaction_costs(transaction)

    assert not error_reporter.has_errors_for(transaction.transaction_id)
    assert transaction.net_cost == Decimal("-60")
    assert transaction.realized_gain_loss == Decimal("290.0")
    assert transaction.realized_capital_pnl_base == Decimal("270")
    assert transaction.realized_fx_pnl_base == Decimal("20")
    assert transaction.realized_total_pnl_base == Decimal("290.0")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"allocated_cost_basis_local": None}, "allocated_cost_basis_local is required"),
        ({"quantity": Decimal("1")}, "quantity_delta must be 0"),
        ({"price": Decimal("1")}, "price must be 0"),
        ({"gross_transaction_amount": Decimal("0")}, "gross cash proceeds must be greater"),
    ],
)
def test_cash_consideration_strategy_rejects_incomplete_or_invalid_product_leg(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
    overrides: dict[str, object],
    message: str,
) -> None:
    transaction = _cash_consideration(**overrides)

    cost_calculator.calculate_transaction_costs(transaction)

    assert error_reporter.has_errors_for(transaction.transaction_id)
    assert message in error_reporter.get_errors()[0].error_reason
    assert transaction.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_cash_consideration_strategy_rejects_malformed_persisted_price(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
) -> None:
    transaction = _cash_consideration()
    transaction.price = "not-a-decimal"

    cost_calculator.calculate_transaction_costs(transaction)

    assert error_reporter.has_errors_for(transaction.transaction_id)
    assert "invalid decimal for price" in error_reporter.get_errors()[0].error_reason
    assert transaction.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


@pytest.mark.parametrize(
    ("transaction_type", "component_type", "extra_fields"),
    [
        (
            "FX_SPOT",
            "FX_CASH_SETTLEMENT_BUY",
            {
                "linked_fx_cash_leg_id": "FX-SPOT-SELL-001",
                "fx_cash_leg_role": "BUY",
                "fx_contract_id": None,
                "product_type": "CASH",
            },
        ),
        ("FX_FORWARD", "FX_CONTRACT_CLOSE", {}),
        (
            "FX_SWAP",
            "FX_CONTRACT_CLOSE",
            {
                "swap_event_id": "SWAP-001",
                "near_leg_group_id": "SWAP-001-NEAR",
                "far_leg_group_id": "SWAP-001-FAR",
            },
        ),
    ],
)
def test_fx_strategy_applies_baseline_processing_without_generic_pending_error(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
    transaction_type,
    component_type,
    extra_fields,
):
    fx_transaction = _canonical_fx_transaction(
        transaction_id=f"{transaction_type}-BASELINE-001",
        transaction_type=transaction_type,
        component_type=component_type,
        **extra_fields,
    )

    cost_calculator.calculate_transaction_costs(fx_transaction)

    assert not error_reporter.has_errors_for(fx_transaction.transaction_id)
    assert fx_transaction.gross_cost == Decimal("0")
    assert fx_transaction.net_cost == Decimal("0")
    assert fx_transaction.net_cost_local == Decimal("0")
    assert fx_transaction.realized_gain_loss == Decimal("0")
    assert fx_transaction.realized_gain_loss_local == Decimal("0")
    assert fx_transaction.realized_capital_pnl_local == Decimal("0")
    assert fx_transaction.realized_fx_pnl_local == Decimal("0")
    assert fx_transaction.realized_total_pnl_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


@pytest.mark.parametrize(
    ("component_type", "metadata", "reason_code"),
    [
        (
            "FX_CASH_SETTLEMENT_BUY",
            {},
            "CASH_ACCOUNT_001_INSTRUMENT_AUTHORITY_UNAVAILABLE",
        ),
        (
            "FX_CASH_SETTLEMENT_SELL",
            {"product_type": "EQUITY", "asset_class": "Equity"},
            "CASH_ACCOUNT_002_NON_CASH_INSTRUMENT",
        ),
    ],
)
def test_fx_cash_component_rebuild_fails_closed_without_authoritative_cash_metadata(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
    component_type: str,
    metadata: dict[str, str],
    reason_code: str,
) -> None:
    fx_transaction = _canonical_fx_transaction(
        transaction_id=f"FX-REBUILD-{component_type}",
        transaction_type="FX_SPOT",
        component_type=component_type,
        **metadata,
    )

    cost_calculator.calculate_transaction_costs(fx_transaction)

    assert error_reporter.has_errors_for(fx_transaction.transaction_id)
    assert reason_code in error_reporter.get_errors()[0].error_reason
    assert fx_transaction.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_fx_strategy_preserves_upstream_provided_realized_fx_pnl(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
):
    fx_transaction = _canonical_fx_transaction(
        transaction_id="FX-UPSTREAM-PNL-001",
        fx_realized_pnl_mode=" upstream_provided ",
        realized_capital_pnl_local=Decimal("0"),
        realized_fx_pnl_local=Decimal("1250"),
        realized_capital_pnl_base=Decimal("0"),
        realized_fx_pnl_base=Decimal("1310"),
    )

    cost_calculator.calculate_transaction_costs(fx_transaction)

    assert not error_reporter.has_errors_for("FX-UPSTREAM-PNL-001")
    assert fx_transaction.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
    assert fx_transaction.realized_capital_pnl_local == Decimal("0")
    assert fx_transaction.realized_fx_pnl_local == Decimal("1250")
    assert fx_transaction.realized_total_pnl_local == Decimal("1250")
    assert fx_transaction.realized_capital_pnl_base == Decimal("0")
    assert fx_transaction.realized_fx_pnl_base == Decimal("1310")
    assert fx_transaction.realized_total_pnl_base == Decimal("1310")
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_fx_strategy_rejects_missing_canonical_economic_fields(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
):
    incomplete_fx_transaction = CostBasisTransaction(
        transaction_id="FX-INCOMPLETE-001",
        portfolio_id="PORT-FX",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_type="FX_FORWARD",
        transaction_date=datetime(2026, 7, 1, 9, 0, 0),
        quantity=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
    )

    cost_calculator.calculate_transaction_costs(incomplete_fx_transaction)

    errors = error_reporter.get_errors()
    assert error_reporter.has_errors_for("FX-INCOMPLETE-001")
    assert errors[0].error_reason == (
        "FX validation failed: required canonical FX fields are incomplete."
    )
    assert incomplete_fx_transaction.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_fx_strategy_rejects_invalid_swap_linkage(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
):
    fx_transaction = _canonical_fx_transaction(
        transaction_id="FX-SWAP-BAD-LINKAGE-001",
        transaction_type="FX_SWAP",
    )

    cost_calculator.calculate_transaction_costs(fx_transaction)

    errors = error_reporter.get_errors()
    assert error_reporter.has_errors_for("FX-SWAP-BAD-LINKAGE-001")
    assert "FX_019_MISSING_SWAP_GROUP_IDENTIFIER:swap_event_id" in errors[0].error_reason
    assert fx_transaction.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


@pytest.mark.parametrize(
    ("charge_update", "expected_reason"),
    [
        (
            {"fees": Fees(brokerage=Decimal("1"))},
            "FX_025_NON_ZERO_EMBEDDED_FEE:trade_fee",
        ),
        (
            {"trade_fee": Decimal("0"), "fees": Fees(brokerage=Decimal("1"))},
            "FX_025_NON_ZERO_EMBEDDED_FEE:trade_fee",
        ),
        (
            {"trade_fee": Decimal("1"), "fees": Fees()},
            "FX_025_NON_ZERO_EMBEDDED_FEE:trade_fee",
        ),
        (
            {"withholding_tax_amount": Decimal("1")},
            "FX_026_NON_ZERO_EMBEDDED_TAX:withholding_tax_amount",
        ),
    ],
)
def test_fx_strategy_rejects_embedded_charge_before_cost_updates(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
    charge_update,
    expected_reason,
) -> None:
    fx_transaction = _canonical_fx_transaction(
        transaction_id="FX-EMBEDDED-CHARGE-001",
        **charge_update,
    )

    cost_calculator.calculate_transaction_costs(fx_transaction)

    errors = error_reporter.get_errors()
    assert error_reporter.has_errors_for("FX-EMBEDDED-CHARGE-001")
    assert expected_reason in errors[0].error_reason
    assert fx_transaction.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_fx_strategy_rejects_unsupported_cash_lot_realized_pnl_mode(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
):
    fx_transaction = _canonical_fx_transaction(
        transaction_id="FX-CASH-LOT-MODE-001",
        fx_realized_pnl_mode="CASH_LOT_COST_METHOD",
    )

    cost_calculator.calculate_transaction_costs(fx_transaction)

    errors = error_reporter.get_errors()
    assert error_reporter.has_errors_for("FX-CASH-LOT-MODE-001")
    assert "CASH_LOT_COST_METHOD" in errors[0].error_reason
    assert "supported modes are NONE and UPSTREAM_PROVIDED" in errors[0].error_reason
    assert fx_transaction.net_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_cost_calculator_rejects_other_before_default_costing(
    cost_calculator, mock_disposition_engine, error_reporter
):
    migration_only_transaction = CostBasisTransaction(
        transaction_id="OTHER_MIGRATION_ONLY_01",
        portfolio_id="P1",
        instrument_id="LEGACY",
        security_id="LEGACY",
        transaction_type=" other ",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("1"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(migration_only_transaction)

    assert migration_only_transaction.transaction_type == "OTHER"
    assert error_reporter.has_errors_for("OTHER_MIGRATION_ONLY_01")
    assert "not allowed for production booking" in error_reporter.get_errors()[0].error_reason
    assert "registry_status=migration_only" in error_reporter.get_errors()[0].error_reason
    assert migration_only_transaction.net_cost is None
    assert migration_only_transaction.net_cost_local is None
    assert migration_only_transaction.gross_cost is None
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_buy_strategy_supports_policy_hook_for_accrued_interest_exclusion(
    cost_calculator, mock_disposition_engine
):
    bond_buy = CostBasisTransaction(
        transaction_id="BOND_BUY_01",
        portfolio_id="P_USD",
        instrument_id="UST5Y",
        security_id="S_UST5Y",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("98000"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("40")),
        accrued_interest=Decimal("1250"),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        calculation_policy_id="BUY_EXCLUDE_ACCRUED_INTEREST_FROM_BOOK_COST",
    )

    cost_calculator.calculate_transaction_costs(bond_buy)

    assert bond_buy.net_cost_local == Decimal("98040")
    assert bond_buy.net_cost == Decimal("98040")
    assert bond_buy.realized_gain_loss == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(bond_buy)


def test_buy_strategy_normalizes_policy_hook_for_accrued_interest_exclusion(
    cost_calculator, mock_disposition_engine
):
    bond_buy = CostBasisTransaction(
        transaction_id="BOND_BUY_PADDED_POLICY_01",
        portfolio_id="P_USD",
        instrument_id="UST5Y",
        security_id="S_UST5Y",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("98000"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("40")),
        accrued_interest=Decimal("1250"),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        calculation_policy_id=" buy_exclude_accrued_interest_from_book_cost ",
    )

    cost_calculator.calculate_transaction_costs(bond_buy)

    assert bond_buy.net_cost_local == Decimal("98040")
    assert bond_buy.net_cost == Decimal("98040")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(bond_buy)


def test_buy_strategy_rejects_zero_quantity_with_invariant_error(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_buy = CostBasisTransaction(
        transaction_id="BUY_ZERO_QTY",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("0"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_buy)

    assert error_reporter.has_errors_for("BUY_ZERO_QTY")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_sell_strategy_gain(cost_calculator, mock_disposition_engine, sell_transaction):
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("500"),
        Decimal("500"),
        Decimal("5"),
        None,
    )
    cost_calculator.calculate_transaction_costs(sell_transaction)
    assert sell_transaction.realized_gain_loss == Decimal("297.0")
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(sell_transaction)


def test_sell_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    dual_currency_sell = CostBasisTransaction(
        transaction_id="DC_SELL_01",
        portfolio_id="P_USD",
        instrument_id="AIR.lotus-performance",
        security_id="S_AIR",
        transaction_type="SELL",
        transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("50"),
        gross_transaction_amount=Decimal("8000"),
        trade_currency="EUR",
        fees=Fees(brokerage=Decimal("8")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.20"),
    )
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("8250"),
        Decimal("7500"),
        Decimal("50"),
        None,
    )
    cost_calculator.calculate_transaction_costs(dual_currency_sell)
    assert dual_currency_sell.realized_gain_loss_local == Decimal("492")
    assert dual_currency_sell.realized_gain_loss.quantize(Decimal("0.01")) == Decimal("1340.40")
    assert dual_currency_sell.net_cost == Decimal("-8250")
    assert dual_currency_sell.net_cost_local == Decimal("-7500")


def test_sell_strategy_normalizes_cross_currency_proceeds_and_realized_pnl(
    cost_calculator,
    mock_disposition_engine,
) -> None:
    transaction = CostBasisTransaction(
        transaction_id="SELL_PRECISION_01",
        portfolio_id="P_USD",
        instrument_id="SEC_EUR",
        security_id="SEC_EUR",
        transaction_type="SELL",
        transaction_date=datetime(2026, 7, 28),
        quantity=Decimal("1"),
        gross_transaction_amount=Decimal("1.0000000001"),
        trade_currency="EUR",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0000000001"),
    )
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("0.1000000000"),
        Decimal("0.1000000000"),
        Decimal("1"),
        None,
    )

    cost_calculator.calculate_transaction_costs(transaction)

    assert transaction.realized_gain_loss_local == Decimal("0.9000000001")
    assert transaction.realized_gain_loss == Decimal("0.9000000002")
    assert transaction.net_cost == Decimal("-0.1000000000")
    assert transaction.net_cost_local == Decimal("-0.1000000000")


def test_sell_strategy_rejects_negative_net_proceeds(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_sell = CostBasisTransaction(
        transaction_id="SELL_NEG_PROCEEDS",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="SELL",
        transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("5"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        fees=Fees(brokerage=Decimal("150")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_sell)

    assert error_reporter.has_errors_for("SELL_NEG_PROCEEDS")
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_rejects_non_positive_consumed_quantity(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("500"),
        Decimal("500"),
        Decimal("0"),
        None,
    )

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for("SELL001")


@pytest.mark.parametrize(
    ("disposition_result", "expected_error"),
    [
        (
            (Decimal("0"), Decimal("0"), Decimal("0"), "lot authority unavailable"),
            "lot authority unavailable",
        ),
        (
            (Decimal("-1"), Decimal("1"), Decimal("5"), None),
            "disposed cost basis must be non-negative",
        ),
    ],
)
def test_sell_strategy_fails_closed_on_invalid_disposition_authority(
    cost_calculator,
    mock_disposition_engine,
    error_reporter,
    sell_transaction,
    disposition_result: tuple[Decimal, Decimal, Decimal, str | None],
    expected_error: str,
) -> None:
    mock_disposition_engine.consume_sell_quantity.return_value = disposition_result

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for(sell_transaction.transaction_id)
    assert expected_error in error_reporter.get_errors()[0].error_reason
    assert sell_transaction.net_cost is None
    assert sell_transaction.net_cost_local is None


def test_sell_strategy_rejects_dirty_non_positive_quantity_before_lot_consumption(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    sell_transaction.quantity = Decimal("-5")

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for("SELL001")
    mock_disposition_engine.get_available_quantity.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_blocks_oversold_under_strict_policy(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    mock_disposition_engine.get_available_quantity.return_value = Decimal("3")

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for("SELL001")
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_reports_unsupported_oversold_policy(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    sell_transaction.calculation_policy_id = "SELL_ALLOW_OVERSOLD_POLICY"
    mock_disposition_engine.get_available_quantity.return_value = Decimal("3")

    cost_calculator.calculate_transaction_costs(sell_transaction)

    assert error_reporter.has_errors_for("SELL001")
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_normalizes_oversold_policy(
    cost_calculator, mock_disposition_engine, error_reporter, sell_transaction
):
    sell_transaction.calculation_policy_id = " sell_allow_oversold_policy "
    mock_disposition_engine.get_available_quantity.return_value = Decimal("3")

    cost_calculator.calculate_transaction_costs(sell_transaction)

    errors = error_reporter.get_errors()
    assert error_reporter.has_errors_for("SELL001")
    assert "oversold policy is configured but not supported" in errors[0].error_reason
    mock_disposition_engine.consume_sell_quantity.assert_not_called()


def test_sell_strategy_multi_lot_fifo():
    error_reporter = CostCalculationErrorCollector()
    fifo_strategy = FIFOBasisStrategy()
    disposition_engine = LotDispositionEngine(cost_basis_strategy=fifo_strategy)
    cost_calculator = CostBasisCalculator(
        disposition_engine=disposition_engine, error_reporter=error_reporter
    )
    buy_txn_1 = CostBasisTransaction(
        transaction_id="BUY001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(buy_txn_1)
    buy_txn_2 = CostBasisTransaction(
        transaction_id="BUY002",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("50"),
        gross_transaction_amount=Decimal("600"),
        net_cost=Decimal("600"),
        net_cost_local=Decimal("600"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(buy_txn_2)
    sell_txn = CostBasisTransaction(
        transaction_id="SELL001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="SELL",
        transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("120"),
        gross_transaction_amount=Decimal("1800"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(sell_txn)
    assert sell_txn.realized_gain_loss == Decimal("560")
    assert not error_reporter.has_errors()
    assert disposition_engine.get_available_quantity("P1", "AAPL") == Decimal("30")


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected_cost", "expected_pnl"),
    [
        ("MATURITY_REDEMPTION", "100", "97", "3"),
        ("CALL_REDEMPTION", "100", "97", "3"),
        ("PARTIAL_REDEMPTION", "40", "38.8", "1.2"),
    ],
)
def test_redemption_strategy_consumes_fifo_lots_and_calculates_principal_only_pnl(
    transaction_type: str,
    quantity: str,
    expected_cost: str,
    expected_pnl: str,
) -> None:
    errors = CostCalculationErrorCollector()
    disposition = LotDispositionEngine(cost_basis_strategy=FIFOBasisStrategy())
    calculator = CostBasisCalculator(disposition_engine=disposition, error_reporter=errors)
    buy = CostBasisTransaction(
        transaction_id="BUY-RED-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        transaction_type="BUY",
        transaction_date=datetime(2026, 1, 1),
        quantity=Decimal("100"),
        price=Decimal("0.97"),
        gross_transaction_amount=Decimal("97"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal(1),
    )
    calculator.calculate_transaction_costs(buy)
    redemption = CostBasisTransaction(
        transaction_id="RED-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        transaction_type=transaction_type,
        transaction_date=datetime(2026, 6, 30),
        settlement_date=datetime(2026, 7, 2),
        product_type="BOND",
        asset_class="FIXED_INCOME",
        quantity=Decimal(quantity),
        price=Decimal(1),
        gross_transaction_amount=Decimal(quantity),
        principal_proceeds_local=Decimal(quantity),
        accrued_interest_proceeds_local=Decimal("5"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal(1),
    )

    calculator.calculate_transaction_costs(redemption)

    assert not errors.has_errors()
    assert redemption.net_cost_local == -Decimal(expected_cost)
    assert redemption.allocated_cost_basis_local == Decimal(expected_cost)
    assert redemption.realized_capital_pnl_local == Decimal(expected_pnl)
    assert redemption.realized_total_pnl_local == Decimal(expected_pnl)
    assert redemption.realized_fx_pnl_local == Decimal(0)
    assert disposition.get_available_quantity("P1", "BOND-1") == Decimal("100") - Decimal(quantity)
    assert len(disposition.disposal_records()) == 1


def test_redemption_strategy_validates_factor_authority_before_lot_consumption() -> None:
    errors = CostCalculationErrorCollector()
    disposition = MagicMock(spec=LotDispositionEngine)
    disposition.get_available_quantity.return_value = Decimal("100")
    redemption = CostBasisTransaction(
        transaction_id="RED-FACTOR-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        transaction_type="PARTIAL_REDEMPTION",
        transaction_date=datetime(2026, 6, 30),
        settlement_date=datetime(2026, 7, 2),
        product_type="BOND",
        asset_class="FIXED_INCOME",
        quantity=Decimal("20"),
        price=Decimal(1),
        gross_transaction_amount=Decimal("20"),
        old_factor=Decimal(1),
        new_factor=Decimal("0.75"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal(1),
    )

    calculator_module.RedemptionStrategy().calculate_costs(redemption, disposition, errors)

    assert errors.has_errors_for("RED-FACTOR-001")
    disposition.consume_sell_quantity.assert_not_called()


@pytest.mark.parametrize(
    ("product_type", "asset_class"),
    [("EQUITY", "EQUITY"), ("", None)],
)
def test_redemption_strategy_rejects_ineligible_instrument_before_lot_access(
    product_type: str,
    asset_class: str | None,
) -> None:
    errors = CostCalculationErrorCollector()
    disposition = MagicMock(spec=LotDispositionEngine)
    redemption = CostBasisTransaction(
        transaction_id="RED-INELIGIBLE-001",
        portfolio_id="P1",
        instrument_id="SEC-1",
        security_id="SEC-1",
        transaction_type="MATURITY_REDEMPTION",
        transaction_date=datetime(2026, 6, 30),
        settlement_date=datetime(2026, 7, 2),
        product_type=product_type,
        asset_class=asset_class,
        quantity=Decimal("100"),
        price=Decimal(1),
        gross_transaction_amount=Decimal("100"),
        principal_proceeds_local=Decimal("100"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal(1),
    )

    calculator_module.RedemptionStrategy().calculate_costs(redemption, disposition, errors)

    assert errors.has_errors_for(redemption.transaction_id)
    disposition.get_available_quantity.assert_not_called()
    disposition.consume_sell_quantity.assert_not_called()


def test_redemption_strategy_requires_value_date_before_lot_access() -> None:
    errors = CostCalculationErrorCollector()
    disposition = MagicMock(spec=LotDispositionEngine)
    redemption = CostBasisTransaction(
        transaction_id="RED-NO-VALUE-DATE-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        transaction_type="CALL_REDEMPTION",
        transaction_date=datetime(2026, 6, 30),
        product_type="BOND",
        asset_class="FIXED_INCOME",
        quantity=Decimal("100"),
        price=Decimal(1),
        gross_transaction_amount=Decimal("100"),
        principal_proceeds_local=Decimal("100"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal(1),
    )

    calculator_module.RedemptionStrategy().calculate_costs(redemption, disposition, errors)

    assert errors.has_errors_for(redemption.transaction_id)
    disposition.get_available_quantity.assert_not_called()
    disposition.consume_sell_quantity.assert_not_called()


def test_redemption_strategy_derives_zero_placeholder_quantity_from_factor_authority() -> None:
    errors = CostCalculationErrorCollector()
    disposition = LotDispositionEngine(cost_basis_strategy=FIFOBasisStrategy())
    calculator = CostBasisCalculator(disposition_engine=disposition, error_reporter=errors)
    calculator.calculate_transaction_costs(
        CostBasisTransaction(
            transaction_id="BUY-FACTOR-001",
            portfolio_id="P1",
            instrument_id="BOND-1",
            security_id="BOND-1",
            transaction_type="BUY",
            transaction_date=datetime(2026, 1, 1),
            quantity=Decimal("100"),
            price=Decimal(1),
            gross_transaction_amount=Decimal("100"),
            trade_currency="USD",
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal(1),
        )
    )
    redemption = CostBasisTransaction(
        transaction_id="RED-FACTOR-ONLY-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        transaction_type="PARTIAL_REDEMPTION",
        transaction_date=datetime(2026, 6, 30),
        settlement_date=datetime(2026, 7, 2),
        product_type="BOND",
        asset_class="FIXED_INCOME",
        quantity=Decimal(0),
        price=Decimal(1),
        gross_transaction_amount=Decimal("25"),
        principal_proceeds_local=Decimal("25"),
        old_factor=Decimal(1),
        new_factor=Decimal("0.75"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal(1),
    )

    calculator.calculate_transaction_costs(redemption)

    assert not errors.has_errors()
    assert redemption.quantity == Decimal("25.0000000000")
    assert redemption.allocated_cost_basis_local == Decimal("25.0000000000")
    assert disposition.get_available_quantity("P1", "BOND-1") == Decimal("75.0000000000")
    assert disposition.disposal_records()[0].result.consumed_quantity == Decimal("25.0000000000")


def test_partial_redemption_strategy_consumes_average_cost_pool() -> None:
    errors = CostCalculationErrorCollector()
    disposition = LotDispositionEngine(cost_basis_strategy=AverageCostBasisStrategy())
    calculator = CostBasisCalculator(disposition_engine=disposition, error_reporter=errors)
    for transaction_id, gross_amount in (("BUY-1", "40"), ("BUY-2", "60")):
        calculator.calculate_transaction_costs(
            CostBasisTransaction(
                transaction_id=transaction_id,
                portfolio_id="P1",
                instrument_id="BOND-1",
                security_id="BOND-1",
                transaction_type="BUY",
                transaction_date=datetime(2026, 1, 1),
                quantity=Decimal("50"),
                price=Decimal(gross_amount) / Decimal("50"),
                gross_transaction_amount=Decimal(gross_amount),
                trade_currency="USD",
                portfolio_base_currency="USD",
                transaction_fx_rate=Decimal(1),
            )
        )
    redemption = CostBasisTransaction(
        transaction_id="RED-AVCO-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        transaction_type="PARTIAL_REDEMPTION",
        transaction_date=datetime(2026, 6, 30),
        settlement_date=datetime(2026, 7, 2),
        product_type="BOND",
        asset_class="FIXED_INCOME",
        quantity=Decimal("25"),
        price=Decimal("1.2"),
        gross_transaction_amount=Decimal("30"),
        principal_proceeds_local=Decimal("30"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal(1),
    )

    calculator.calculate_transaction_costs(redemption)

    assert not errors.has_errors()
    assert redemption.allocated_cost_basis_local == Decimal("25.0000000000")
    assert redemption.realized_capital_pnl_local == Decimal("5.0000000000")
    assert disposition.get_available_quantity("P1", "BOND-1") == Decimal("75.0000000000")
    assert disposition.disposal_records()[0].result.consumed_quantity == Decimal("25.0000000000")


def test_deposit_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    deposit_transaction = CostBasisTransaction(
        transaction_id="DEPOSIT001",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="DEPOSIT",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("10000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )
    cost_calculator.calculate_transaction_costs(deposit_transaction)
    assert deposit_transaction.net_cost == Decimal("10000")
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert call_args.quantity == Decimal("10000")


def test_deposit_strategy_uses_quantity_when_gross_amount_is_zero(
    cost_calculator, mock_disposition_engine
):
    deposit_transaction = CostBasisTransaction(
        transaction_id="DEPOSIT_QTY_AMOUNT_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="DEPOSIT",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )

    cost_calculator.calculate_transaction_costs(deposit_transaction)

    assert deposit_transaction.gross_cost == Decimal("10000")
    assert deposit_transaction.net_cost_local == Decimal("10000")
    assert deposit_transaction.net_cost == Decimal("10000.0")
    mock_disposition_engine.add_buy_lot.assert_called_once()
    cash_lot = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert cash_lot.quantity == Decimal("10000")


def test_deposit_strategy_normalizes_blank_gross_amount_to_quantity_once(
    cost_calculator, mock_disposition_engine
):
    deposit_transaction = CostBasisTransaction(
        transaction_id="DEPOSIT_BLANK_GROSS_AMOUNT_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="DEPOSIT",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )
    quantity = _StringCountedAmount("10000")
    deposit_transaction.gross_transaction_amount = " "
    deposit_transaction.quantity = quantity

    cost_calculator.calculate_transaction_costs(deposit_transaction)

    assert deposit_transaction.gross_cost == Decimal("10000")
    assert deposit_transaction.net_cost_local == Decimal("10000")
    assert deposit_transaction.net_cost == Decimal("10000.0")
    assert quantity.string_call_count == 1
    cash_lot = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert cash_lot.quantity == Decimal("10000")


def test_deposit_strategy_uses_magnitude_for_signed_legacy_cash_amount(
    cost_calculator, mock_disposition_engine
):
    deposit_transaction = CostBasisTransaction(
        transaction_id="DEPOSIT_SIGNED_LEGACY_AMOUNT_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="DEPOSIT",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10000"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("10000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )
    deposit_transaction.gross_transaction_amount = Decimal("-10000")

    cost_calculator.calculate_transaction_costs(deposit_transaction)

    assert deposit_transaction.gross_cost == Decimal("10000")
    assert deposit_transaction.net_cost_local == Decimal("10000")
    assert deposit_transaction.net_cost == Decimal("10000.0")
    cash_lot = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert cash_lot.quantity == Decimal("10000")


def test_dividend_transaction_has_zero_cost(cost_calculator, mock_disposition_engine):
    dividend_transaction = CostBasisTransaction(
        transaction_id="DIV001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="DIVIDEND",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("500.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(dividend_transaction)
    assert dividend_transaction.net_cost == Decimal("0")
    assert dividend_transaction.realized_gain_loss == Decimal("0")
    assert dividend_transaction.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_accepts_string_zero_price(
    cost_calculator, mock_disposition_engine, error_reporter
):
    dividend_transaction = CostBasisTransaction(
        transaction_id="DIV_STR_PRICE_0",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="DIVIDEND",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price="0",
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(dividend_transaction)
    assert not error_reporter.has_errors_for("DIV_STR_PRICE_0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_rejects_non_zero_quantity(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_dividend = CostBasisTransaction(
        transaction_id="DIV_BAD_QTY",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="DIVIDEND",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("1"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_dividend)
    assert error_reporter.has_errors_for("DIV_BAD_QTY")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_rejects_non_zero_price(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_dividend = CostBasisTransaction(
        transaction_id="DIV_BAD_PRICE",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="DIVIDEND",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_dividend)
    assert error_reporter.has_errors_for("DIV_BAD_PRICE")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_dividend_strategy_rejects_non_positive_gross_amount(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_dividend = CostBasisTransaction(
        transaction_id="DIV_BAD_GROSS",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="DIVIDEND",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_dividend)
    assert error_reporter.has_errors_for("DIV_BAD_GROSS")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_transaction_has_zero_cost_and_explicit_zero_realized_pnl(
    cost_calculator, mock_disposition_engine
):
    interest_transaction = CostBasisTransaction(
        transaction_id="INT001",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type="INTEREST",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(interest_transaction)
    assert interest_transaction.net_cost == Decimal("0")
    assert interest_transaction.realized_gain_loss == Decimal("0")
    assert interest_transaction.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_rejects_non_zero_quantity(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_interest = CostBasisTransaction(
        transaction_id="INT_BAD_QTY",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type="INTEREST",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("1"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_interest)
    assert error_reporter.has_errors_for("INT_BAD_QTY")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_rejects_non_zero_price(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_interest = CostBasisTransaction(
        transaction_id="INT_BAD_PRICE",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type="INTEREST",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("5"),
        gross_transaction_amount=Decimal("50.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_interest)
    assert error_reporter.has_errors_for("INT_BAD_PRICE")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_rejects_non_positive_gross_amount(
    cost_calculator, mock_disposition_engine, error_reporter
):
    invalid_interest = CostBasisTransaction(
        transaction_id="INT_BAD_GROSS",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type="INTEREST",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(invalid_interest)
    assert error_reporter.has_errors_for("INT_BAD_GROSS")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_allows_expense_direction_baseline(
    cost_calculator, mock_disposition_engine, error_reporter
):
    expense_interest = CostBasisTransaction(
        transaction_id="INT_EXPENSE_OK",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type="INTEREST",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        interest_direction="EXPENSE",
    )

    cost_calculator.calculate_transaction_costs(expense_interest)
    assert not error_reporter.has_errors_for("INT_EXPENSE_OK")
    assert expense_interest.realized_gain_loss == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()


def test_interest_strategy_normalizes_direction(cost_calculator, error_reporter):
    expense_interest = CostBasisTransaction(
        transaction_id="INT_EXPENSE_PADDED_OK",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type="INTEREST",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        interest_direction=" expense ",
    )

    cost_calculator.calculate_transaction_costs(expense_interest)

    assert not error_reporter.has_errors_for("INT_EXPENSE_PADDED_OK")
    assert expense_interest.realized_gain_loss == Decimal("0")


def test_interest_strategy_rejects_unknown_direction(cost_calculator, error_reporter):
    invalid_direction = CostBasisTransaction(
        transaction_id="INT_BAD_DIR",
        portfolio_id="P1",
        instrument_id="BOND_USD",
        security_id="S_BOND",
        transaction_type="INTEREST",
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("25.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        interest_direction="UNKNOWN",
    )

    cost_calculator.calculate_transaction_costs(invalid_direction)
    assert error_reporter.has_errors_for("INT_BAD_DIR")


def test_transfer_in_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    transfer_in_transaction = CostBasisTransaction(
        transaction_id="TRANSFER_IN_01",
        portfolio_id="P1",
        instrument_id="IBM",
        security_id="S_IBM",
        transaction_type="TRANSFER_IN",
        transaction_date=datetime(2023, 2, 1),
        quantity=Decimal("100"),
        price=Decimal("150"),
        gross_transaction_amount=Decimal("15000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )
    cost_calculator.calculate_transaction_costs(transfer_in_transaction)
    assert transfer_in_transaction.net_cost == Decimal("15000")
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert call_args.quantity == Decimal("100")
    assert call_args.net_cost == Decimal("15000")


def test_transfer_out_strategy_consumes_lot_without_pnl(cost_calculator, mock_disposition_engine):
    """
    Tests that a TRANSFER_OUT transaction consumes a cost lot but does not generate P&L.
    """
    # Arrange
    transfer_out_transaction = CostBasisTransaction(
        transaction_id="TRANSFER_OUT_01",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="TRANSFER_OUT",
        transaction_date=datetime(2023, 2, 15),
        quantity=Decimal("20"),
        price=Decimal("160"),
        gross_transaction_amount=Decimal("3200"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    # Simulate the disposition engine returning the cost of the transferred shares
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("3000"),
        Decimal("3000"),
        Decimal("20"),
        None,
    )

    # Act
    cost_calculator.calculate_transaction_costs(transfer_out_transaction)

    # Assert
    # It should have called the disposition engine to "consume" the shares
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(transfer_out_transaction)

    # Crucially, it should NOT have calculated a realized gain/loss
    assert transfer_out_transaction.realized_gain_loss is None


# --- NEW FAILING TEST ---
def test_withdrawal_strategy_consumes_lot_without_pnl(cost_calculator, mock_disposition_engine):
    """
    Tests that a WITHDRAWAL transaction consumes a cash cost lot but does not generate P&L.
    This will fail with the current DefaultStrategy mapping.
    """
    # Arrange
    withdrawal_transaction = CostBasisTransaction(
        transaction_id="WITHDRAWAL_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="WITHDRAWAL",
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("500"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )

    # Simulate the disposition engine returning the cost of the withdrawn cash
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("500"),
        Decimal("500"),
        Decimal("500"),
        None,
    )

    # Act
    cost_calculator.calculate_transaction_costs(withdrawal_transaction)

    # Assert
    # Cash outflow is handled with cash semantics rather than strict security-lot disposal.
    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert withdrawal_transaction.realized_gain_loss is None
    assert withdrawal_transaction.net_cost == Decimal("-500")
    assert withdrawal_transaction.net_cost_local == Decimal("-500")


def test_withdrawal_strategy_uses_quantity_when_gross_amount_is_zero(
    cost_calculator, mock_disposition_engine
):
    withdrawal_transaction = CostBasisTransaction(
        transaction_id="WITHDRAWAL_QTY_AMOUNT_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="WITHDRAWAL",
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("500"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )

    cost_calculator.calculate_transaction_costs(withdrawal_transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert withdrawal_transaction.realized_gain_loss is None
    assert withdrawal_transaction.net_cost == Decimal("-500.0")
    assert withdrawal_transaction.net_cost_local == Decimal("-500")


def test_withdrawal_strategy_uses_magnitude_for_signed_legacy_cash_amount(
    cost_calculator, mock_disposition_engine
):
    withdrawal_transaction = CostBasisTransaction(
        transaction_id="WITHDRAWAL_SIGNED_LEGACY_AMOUNT_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="WITHDRAWAL",
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("500"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )
    withdrawal_transaction.gross_transaction_amount = Decimal("-500")

    cost_calculator.calculate_transaction_costs(withdrawal_transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert withdrawal_transaction.realized_gain_loss is None
    assert withdrawal_transaction.net_cost == Decimal("-500.0")
    assert withdrawal_transaction.net_cost_local == Decimal("-500")


def test_cash_withdrawal_detection_normalizes_source_vocabulary(
    cost_calculator, mock_disposition_engine
):
    withdrawal_transaction = CostBasisTransaction(
        transaction_id="WITHDRAWAL_PADDED_CASH_01",
        portfolio_id="P1",
        instrument_id=" cash_usd ",
        security_id=" cash_usd ",
        transaction_type=" withdrawal ",
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("500"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("0"),
        trade_currency=" usd ",
        portfolio_base_currency=" USD ",
        transaction_fx_rate=None,
        product_type=" cash ",
        asset_class=" cash ",
    )

    cost_calculator.calculate_transaction_costs(withdrawal_transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert withdrawal_transaction.transaction_type == "WITHDRAWAL"
    assert withdrawal_transaction.trade_currency == "USD"
    assert withdrawal_transaction.portfolio_base_currency == "USD"
    assert withdrawal_transaction.transaction_fx_rate == Decimal("1")
    assert withdrawal_transaction.realized_gain_loss is None
    assert withdrawal_transaction.net_cost == Decimal("-500")
    assert withdrawal_transaction.net_cost_local == Decimal("-500")


@pytest.mark.parametrize("transaction_type", ["FEE", "TAX"])
def test_cash_expense_flows_use_cash_outflow_strategy(
    cost_calculator, mock_disposition_engine, transaction_type
):
    expense_transaction = CostBasisTransaction(
        transaction_id=f"{transaction_type}_CASH_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type=transaction_type,
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("1"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )

    cost_calculator.calculate_transaction_costs(expense_transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert expense_transaction.realized_gain_loss is None
    assert expense_transaction.net_cost == Decimal("-25.0")
    assert expense_transaction.net_cost_local == Decimal("-25")


def test_cash_fee_outflow_includes_fee_components(cost_calculator, mock_disposition_engine):
    fee_transaction = CostBasisTransaction(
        transaction_id="FEE_CASH_COMPONENTS_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="FEE",
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("1"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
        fees=Fees(brokerage=Decimal("1.50"), other_fees=Decimal("0.25")),
    )

    cost_calculator.calculate_transaction_costs(fee_transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert fee_transaction.realized_gain_loss is None
    assert fee_transaction.net_cost == Decimal("-26.750")
    assert fee_transaction.net_cost_local == Decimal("-26.75")


@pytest.mark.parametrize("transaction_type", ["DEPOSIT", "WITHDRAWAL", "FEE", "TAX"])
def test_non_cash_account_booking_is_rejected_without_default_cost(
    transaction_type, cost_calculator, mock_disposition_engine, error_reporter
):
    transaction = CostBasisTransaction(
        transaction_id=f"{transaction_type}_NON_CASH_01",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="AAPL",
        transaction_type=transaction_type,
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("1"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Equity",
        asset_class="Equity",
    )

    cost_calculator.calculate_transaction_costs(transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert error_reporter.has_errors_for(f"{transaction_type}_NON_CASH_01")
    assert error_reporter.get_errors()[0].error_reason.startswith(
        "CASH_ACCOUNT_002_NON_CASH_INSTRUMENT:"
    )
    assert transaction.net_cost is None
    assert transaction.net_cost_local is None


def test_cash_sell_strategy_avoids_strict_oversell_for_cash_instrument(
    cost_calculator, mock_disposition_engine, error_reporter
):
    cash_sell = CostBasisTransaction(
        transaction_id="CASH_SELL_01",
        portfolio_id="P1",
        instrument_id="CASH_USD",
        security_id="CASH_USD",
        transaction_type="SELL",
        transaction_date=datetime(2023, 2, 20),
        quantity=Decimal("500"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        product_type="Cash",
        asset_class="Cash",
    )
    mock_disposition_engine.get_available_quantity.return_value = Decimal("0")

    cost_calculator.calculate_transaction_costs(cash_sell)

    assert not error_reporter.has_errors_for("CASH_SELL_01")
    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    assert cash_sell.realized_gain_loss is None
    assert cash_sell.net_cost == Decimal("-500")
    assert cash_sell.net_cost_local == Decimal("-500")


def test_spin_off_basis_only_strategy_reduces_cost_without_lot_consumption(
    cost_calculator, mock_disposition_engine
):
    mock_disposition_engine.transfer_basis_out.return_value = LotBasisTransferResult(
        transferred_cost_local=Decimal("2500"),
        transferred_cost_base=Decimal("2500"),
        allocations=(
            SourceLotBasisTransferAllocation(
                allocation_ordinal=1,
                source_lot_id="LOT-BUY-1",
                source_transaction_id="BUY-1",
                source_acquisition_date=date(2023, 1, 1),
                retained_quantity=Decimal("100"),
                source_cost_local_before=Decimal("3500"),
                source_cost_base_before=Decimal("3500"),
                transferred_cost_local=Decimal("2500"),
                transferred_cost_base=Decimal("2500"),
                retained_cost_local=Decimal("1000"),
                retained_cost_base=Decimal("1000"),
            ),
        ),
    )
    spin_off_transaction = CostBasisTransaction(
        transaction_id="SPIN_OFF_01",
        portfolio_id="P1",
        instrument_id="SRC_SEC",
        security_id="SRC_SEC",
        transaction_type="SPIN_OFF",
        transaction_date=datetime(2023, 3, 1),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("2500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(spin_off_transaction)

    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    mock_disposition_engine.transfer_basis_out.assert_called_once_with(
        spin_off_transaction,
        cost_base=Decimal("2500.0"),
        cost_local=Decimal("2500"),
    )
    assert spin_off_transaction.net_cost == Decimal("-2500")
    assert spin_off_transaction.net_cost_local == Decimal("-2500")
    assert spin_off_transaction.realized_gain_loss is None


def test_spin_in_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    spin_in_transaction = CostBasisTransaction(
        transaction_id="SPIN_IN_01",
        portfolio_id="P1",
        instrument_id="NEW_SEC",
        security_id="NEW_SEC",
        transaction_type="SPIN_IN",
        transaction_date=datetime(2023, 3, 1),
        quantity=Decimal("20"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("2500"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(spin_in_transaction)

    mock_disposition_engine.add_buy_lot.assert_called_once_with(spin_in_transaction)
    assert spin_in_transaction.net_cost == Decimal("2500")


@pytest.mark.parametrize(
    "transaction_type",
    [
        "SPLIT",
        "REVERSE_SPLIT",
        "CONSOLIDATION",
        "BONUS_ISSUE",
        "STOCK_DIVIDEND",
    ],
)
def test_same_instrument_ca_restatement_types_preserve_total_basis(
    cost_calculator, mock_disposition_engine, transaction_type
):
    signed_delta = (
        Decimal("-10") if transaction_type in {"REVERSE_SPLIT", "CONSOLIDATION"} else Decimal("10")
    )
    mock_disposition_engine.restate_lot_quantities.return_value = LotRestatement.from_signed_delta(
        quantity_before=Decimal("100"),
        signed_quantity_delta=signed_delta,
    )
    txn = CostBasisTransaction(
        transaction_id=f"{transaction_type}_01",
        portfolio_id="P1",
        instrument_id="EQ1",
        security_id="EQ1",
        transaction_type=transaction_type,
        transaction_date=datetime(2024, 1, 1),
        quantity=Decimal("10"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0"),
    )

    cost_calculator.calculate_transaction_costs(txn)

    assert txn.net_cost == Decimal("0")
    assert txn.net_cost_local == Decimal("0")
    assert txn.gross_cost == Decimal("0")
    assert txn.realized_gain_loss == Decimal("0")
    assert txn.realized_gain_loss_local == Decimal("0")
    mock_disposition_engine.add_buy_lot.assert_not_called()
    mock_disposition_engine.consume_sell_quantity.assert_not_called()
    mock_disposition_engine.restate_lot_quantities.assert_called_once_with(
        txn,
        signed_quantity_delta=signed_delta,
    )
    assert txn.lot_restatement == {
        "quantity_before": Decimal("100"),
        "quantity_after": Decimal("100") + signed_delta,
        "factor_numerator": Decimal("100") + signed_delta,
        "factor_denominator": Decimal("100"),
    }
    assert txn.calculation_lineage is not None


def test_rights_delivery_and_allocate_use_inflow_strategy(cost_calculator, mock_disposition_engine):
    for tx_type in ("RIGHTS_ALLOCATE", "RIGHTS_SHARE_DELIVERY"):
        txn = CostBasisTransaction(
            transaction_id=f"{tx_type}_01",
            portfolio_id="P1",
            instrument_id="RIGHTS_SEC",
            security_id="RIGHTS_SEC",
            transaction_type=tx_type,
            transaction_date=datetime(2024, 1, 1),
            quantity=Decimal("5"),
            price=Decimal("0"),
            gross_transaction_amount=Decimal("0"),
            trade_currency="USD",
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal("1.0"),
        )
        cost_calculator.calculate_transaction_costs(txn)
    assert mock_disposition_engine.add_buy_lot.call_count >= 2


def test_rights_outflow_types_consume_lots_without_realized_pnl(
    cost_calculator, mock_disposition_engine
):
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("100"),
        Decimal("100"),
        Decimal("1"),
        None,
    )
    for tx_type in ("RIGHTS_SUBSCRIBE", "RIGHTS_OVERSUBSCRIBE", "RIGHTS_SELL", "RIGHTS_EXPIRE"):
        txn = CostBasisTransaction(
            transaction_id=f"{tx_type}_01",
            portfolio_id="P1",
            instrument_id="RIGHTS_SEC",
            security_id="RIGHTS_SEC",
            transaction_type=tx_type,
            transaction_date=datetime(2024, 1, 1),
            quantity=Decimal("1"),
            price=Decimal("0"),
            gross_transaction_amount=Decimal("0"),
            trade_currency="USD",
            portfolio_base_currency="USD",
            transaction_fx_rate=Decimal("1.0"),
        )
        cost_calculator.calculate_transaction_costs(txn)
        assert txn.realized_gain_loss is None
