from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from portfolio_common.events import TransactionEvent
from pydantic import ValidationError


def test_transaction_event_normalizes_control_codes_without_defaulting() -> None:
    event = TransactionEvent(
        transaction_id="EVENT_CONTROL_001",
        portfolio_id="PORT_META_001",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 3, 1, 10, 0),
        transaction_type=" dividend ",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1000.0"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode=" upstream_provided ",
        movement_direction=" inflow ",
        originating_transaction_type=" buy ",
        adjustment_reason=" buy_settlement ",
        link_type=" buy_to_cash ",
        interest_direction=" expense ",
        component_type=" fx_cash_settlement_buy ",
        fx_cash_leg_role=" buy ",
        settlement_status=" settled ",
        fx_rate_quote_convention=" quote_per_base ",
        spot_exposure_model=" fx_contract ",
        fx_realized_pnl_mode=" upstream_provided ",
        child_role=" source_position_close ",
        synthetic_flow_valuation_method=" mvt_price_x_qty ",
        synthetic_flow_classification=" position_transfer_out ",
        synthetic_flow_price_source=" upstream ",
        synthetic_flow_fx_source=" fx_service ",
        synthetic_flow_source=" upstream_provided ",
    )
    implicit_event = TransactionEvent(
        transaction_id="EVENT_CONTROL_002",
        portfolio_id="PORT_META_001",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 3, 1, 10, 0),
        transaction_type=" dividend ",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1000.0"),
        trade_currency="USD",
        currency="USD",
    )

    assert event.transaction_type == "DIVIDEND"
    assert event.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert event.movement_direction == "INFLOW"
    assert event.originating_transaction_type == "BUY"
    assert event.adjustment_reason == "BUY_SETTLEMENT"
    assert event.link_type == "BUY_TO_CASH"
    assert event.interest_direction == "EXPENSE"
    assert event.component_type == "FX_CASH_SETTLEMENT_BUY"
    assert event.fx_cash_leg_role == "BUY"
    assert event.settlement_status == "SETTLED"
    assert event.fx_rate_quote_convention == "QUOTE_PER_BASE"
    assert event.spot_exposure_model == "FX_CONTRACT"
    assert event.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
    assert event.child_role == "SOURCE_POSITION_CLOSE"
    assert event.synthetic_flow_valuation_method == "MVT_PRICE_X_QTY"
    assert event.synthetic_flow_classification == "POSITION_TRANSFER_OUT"
    assert event.synthetic_flow_price_source == "UPSTREAM"
    assert event.synthetic_flow_fx_source == "FX_SERVICE"
    assert event.synthetic_flow_source == "UPSTREAM_PROVIDED"
    assert implicit_event.cash_entry_mode is None
    assert implicit_event.fx_realized_pnl_mode is None


def test_transaction_event_aggregates_trade_fee_from_components() -> None:
    event = TransactionEvent(
        transaction_id="EVENT_FEE_COMPONENTS_001",
        portfolio_id="PORT_META_001",
        instrument_id="SEC_EQ_US_001",
        security_id="SEC_EQ_US_001",
        transaction_date=datetime(2026, 3, 1, 10, 0),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000.0"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("0.00"),
        brokerage=Decimal("2.50"),
        stamp_duty=Decimal("1.20"),
        exchange_fee=Decimal("0.70"),
        gst=Decimal("0.45"),
        other_fees=Decimal("0.15"),
    )

    assert event.trade_fee == Decimal("5.00")


def test_transaction_event_rejects_negative_trade_fee() -> None:
    with pytest.raises(ValidationError, match="trade_fee"):
        TransactionEvent(
            transaction_id="EVENT_NEGATIVE_FEE_001",
            portfolio_id="PORT_META_001",
            instrument_id="SEC_EQ_US_001",
            security_id="SEC_EQ_US_001",
            transaction_date=datetime(2026, 3, 1, 10, 0),
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000.0"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("-0.01"),
        )


def test_transaction_event_rejects_negative_fee_component() -> None:
    with pytest.raises(ValidationError, match="brokerage"):
        TransactionEvent(
            transaction_id="EVENT_NEGATIVE_COMPONENT_001",
            portfolio_id="PORT_META_001",
            instrument_id="SEC_EQ_US_001",
            security_id="SEC_EQ_US_001",
            transaction_date=datetime(2026, 3, 1, 10, 0),
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000.0"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0.00"),
            brokerage=Decimal("-0.01"),
        )


def test_transaction_event_rejects_negative_core_amount() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to zero"):
        TransactionEvent(
            transaction_id="EVENT_NEGATIVE_AMOUNT_001",
            portfolio_id="PORT_META_001",
            instrument_id="SEC_EQ_US_001",
            security_id="SEC_EQ_US_001",
            transaction_date=datetime(2026, 3, 1, 10, 0),
            transaction_type="BUY",
            quantity=Decimal("-1"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000.0"),
            trade_currency="USD",
            currency="USD",
        )


def test_transaction_event_rejects_nonpositive_fx_amounts_and_rates() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        TransactionEvent(
            transaction_id="EVENT_NONPOSITIVE_FX_001",
            portfolio_id="PORT_META_001",
            instrument_id="FX_EUR_USD_001",
            security_id="FX_EUR_USD_001",
            transaction_date=datetime(2026, 3, 1, 10, 0),
            transaction_type="FX_FORWARD",
            quantity=Decimal("0"),
            price=Decimal("0"),
            gross_transaction_amount=Decimal("0"),
            trade_currency="USD",
            currency="USD",
            pair_base_currency="EUR",
            pair_quote_currency="USD",
            buy_currency="USD",
            sell_currency="EUR",
            buy_amount=Decimal("0"),
            sell_amount=Decimal("1000000"),
            contract_rate=Decimal("1.095"),
        )
