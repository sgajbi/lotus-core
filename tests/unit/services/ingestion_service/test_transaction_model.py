from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.ingestion_service.app.DTOs.transaction_dto import Transaction


def test_transaction_model_success():
    """
    Tests that the Transaction model successfully validates a correct data payload.
    """
    valid_payload = {
        "transaction_id": "test_txn_001",
        "portfolio_id": "test_port_001",
        "instrument_id": "AAPL",
        "security_id": "SEC_AAPL",
        "transaction_date": "2025-07-21T00:00:00",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "150.0",
        "gross_transaction_amount": "1500.0",
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": "5.0",
        "settlement_date": "2025-07-23T00:00:00",
        "created_at": datetime.now(),
    }
    transaction = Transaction(**valid_payload)
    assert transaction.transaction_id == "test_txn_001"
    assert transaction.quantity == Decimal("10.0")


def test_transaction_model_missing_field_fails():
    """
    Tests that the Transaction model fails validation if a required field is missing.
    """
    invalid_payload = {
        "transaction_id": "test_txn_002",
        "portfolio_id": "test_port_002",
        "security_id": "SEC_GOOG",
        "transaction_date": "2025-07-22T00:00:00",
        "transaction_type": "SELL",
        "quantity": "5.0",
        "price": "200.0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
    }
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**invalid_payload)
    assert any("instrument_id" in err.get("loc", ()) for err in exc_info.value.errors())


def test_transaction_model_invalid_gross_amount_fails():
    """
    Tests that the Transaction model fails validation for invalid
    gross_transaction_amount (zero or negative).
    """
    base_payload = {
        "transaction_id": "txn_invalid_gross_amount",
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": "2025-01-01T00:00:00",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "100.0",
        "trade_currency": "USD",
        "currency": "USD",
    }
    payload_zero_gross = {**base_payload, "gross_transaction_amount": "0"}
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload_zero_gross)
    assert any(
        "greater than 0" in err["msg"] and "gross_transaction_amount" in str(err.get("loc"))
        for err in exc_info.value.errors()
    )


def test_transaction_model_invalid_trade_fee_fails():
    """
    Tests that the Transaction model fails validation for invalid trade_fee (negative).
    """
    base_payload = {
        "transaction_id": "txn_invalid_fee",
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": "2025-01-01T00:00:00",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "100.0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
    }
    payload_neg_fee = {**base_payload, "trade_fee": "-5.0"}
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload_neg_fee)
    assert any(
        "greater than or equal to 0" in err["msg"] and "trade_fee" in str(err.get("loc"))
        for err in exc_info.value.errors()
    )


def test_transaction_model_aggregates_trade_fee_from_components() -> None:
    payload = {
        "transaction_id": "txn_fee_components",
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": "2025-01-01T00:00:00",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "100.0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": "0.00",
        "brokerage": "2.50",
        "stamp_duty": "1.20",
        "exchange_fee": "0.70",
        "gst": "0.45",
        "other_fees": "0.15",
    }

    transaction = Transaction(**payload)

    assert transaction.trade_fee == Decimal("5.00")


def test_transaction_model_non_numeric_input_fails():
    """
    Tests that the Transaction model fails validation for non-numeric input for Decimal fields.
    """
    base_payload = {
        "transaction_id": "txn_non_numeric",
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": "2025-01-01T00:00:00",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "100.0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
    }
    payload_non_numeric_qty = {**base_payload, "quantity": "abc"}
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload_non_numeric_qty)
    assert any(
        "valid decimal" in err["msg"] and "quantity" in str(err.get("loc"))
        for err in exc_info.value.errors()
    )


def test_transaction_model_dividend_with_zero_qty_price_succeeds():
    """
    Tests that a DIVIDEND transaction with zero quantity and price is considered valid.
    """
    dividend_payload = {
        "transaction_id": "test_div_001",
        "portfolio_id": "test_port_001",
        "instrument_id": "IBM",
        "security_id": "SEC_IBM",
        "transaction_date": "2025-08-23T00:00:00",
        "transaction_type": "DIVIDEND",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "750.0",
        "trade_currency": "USD",
        "currency": "USD",
    }
    transaction = Transaction(**dividend_payload)
    assert transaction.quantity == Decimal("0")
    assert transaction.price == Decimal("0")


def test_transaction_model_accepts_slice1_canonical_metadata_fields():
    payload = {
        "transaction_id": "BUY_META_001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "SEC_UST_5Y",
        "security_id": "SEC_UST_5Y",
        "transaction_date": "2026-03-01T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "100.0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
        "settlement_date": "2026-03-03T10:00:00Z",
        "economic_event_id": "EVT-2026-00987",
        "linked_transaction_group_id": "LTG-2026-00456",
        "calculation_policy_id": "BUY_DEFAULT_POLICY",
        "calculation_policy_version": "1.0.0",
        "source_system": "OMS_PRIMARY",
    }
    model = Transaction(**payload)
    assert model.economic_event_id == "EVT-2026-00987"
    assert model.linked_transaction_group_id == "LTG-2026-00456"
    assert model.calculation_policy_id == "BUY_DEFAULT_POLICY"


def test_transaction_model_accepts_cross_currency_transaction_fx_rate() -> None:
    payload = {
        "transaction_id": "BUY_EUR_001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "SAP",
        "security_id": "SEC_SAP",
        "transaction_date": "2025-04-20T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "121.4",
        "gross_transaction_amount": "1214.0",
        "trade_currency": "EUR",
        "currency": "EUR",
        "transaction_fx_rate": "1.074352",
    }

    model = Transaction(**payload)

    assert model.trade_currency == "EUR"
    assert model.transaction_fx_rate == Decimal("1.074352")


def test_transaction_model_accepts_cash_entry_mode_and_external_cash_link() -> None:
    payload = {
        "transaction_id": "DIV_CASH_MODE_001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "SEC_EQ_US_001",
        "security_id": "SEC_EQ_US_001",
        "transaction_date": "2026-03-01T10:00:00Z",
        "transaction_type": "DIVIDEND",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
        "cash_entry_mode": "UPSTREAM_PROVIDED",
        "external_cash_transaction_id": "CASH-ENTRY-2026-0001",
    }
    model = Transaction(**payload)
    assert model.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert model.external_cash_transaction_id == "CASH-ENTRY-2026-0001"


def test_transaction_model_normalizes_control_codes_without_defaulting() -> None:
    payload = {
        "transaction_id": "CONTROL_CODE_001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "SEC_EQ_US_001",
        "security_id": "SEC_EQ_US_001",
        "transaction_date": "2026-03-01T10:00:00Z",
        "transaction_type": " dividend ",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
        "cash_entry_mode": " upstream_provided ",
        "movement_direction": " inflow ",
        "originating_transaction_type": " buy ",
        "adjustment_reason": " buy_settlement ",
        "link_type": " buy_to_cash ",
        "interest_direction": " expense ",
        "component_type": " fx_cash_settlement_buy ",
        "fx_cash_leg_role": " buy ",
        "settlement_status": " settled ",
        "fx_rate_quote_convention": " quote_per_base ",
        "spot_exposure_model": " fx_contract ",
        "fx_realized_pnl_mode": " upstream_provided ",
        "child_role": " source_position_close ",
        "synthetic_flow_valuation_method": " mvt_price_x_qty ",
        "synthetic_flow_classification": " position_transfer_out ",
        "synthetic_flow_price_source": " upstream ",
        "synthetic_flow_fx_source": " fx_service ",
        "synthetic_flow_source": " upstream_provided ",
    }

    model = Transaction(**payload)
    implicit_model = Transaction(
        **{
            "transaction_id": "CONTROL_CODE_002",
            "portfolio_id": "PORT_META_001",
            "instrument_id": "SEC_EQ_US_001",
            "security_id": "SEC_EQ_US_001",
            "transaction_date": "2026-03-01T10:00:00Z",
            "transaction_type": " dividend ",
            "quantity": "0",
            "price": "0",
            "gross_transaction_amount": "1000.0",
            "trade_currency": "USD",
            "currency": "USD",
        }
    )

    assert model.transaction_type == "DIVIDEND"
    assert model.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert model.movement_direction == "INFLOW"
    assert model.originating_transaction_type == "BUY"
    assert model.adjustment_reason == "BUY_SETTLEMENT"
    assert model.link_type == "BUY_TO_CASH"
    assert model.interest_direction == "EXPENSE"
    assert model.component_type == "FX_CASH_SETTLEMENT_BUY"
    assert model.fx_cash_leg_role == "BUY"
    assert model.settlement_status == "SETTLED"
    assert model.fx_rate_quote_convention == "QUOTE_PER_BASE"
    assert model.spot_exposure_model == "FX_CONTRACT"
    assert model.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
    assert model.child_role == "SOURCE_POSITION_CLOSE"
    assert model.synthetic_flow_valuation_method == "MVT_PRICE_X_QTY"
    assert model.synthetic_flow_classification == "POSITION_TRANSFER_OUT"
    assert model.synthetic_flow_price_source == "UPSTREAM"
    assert model.synthetic_flow_fx_source == "FX_SERVICE"
    assert model.synthetic_flow_source == "UPSTREAM_PROVIDED"
    assert implicit_model.cash_entry_mode is None
    assert implicit_model.fx_realized_pnl_mode is None


def test_transaction_model_accepts_interest_semantic_fields() -> None:
    payload = {
        "transaction_id": "INT_FIELDS_001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "BOND_USD_001",
        "security_id": "BOND_USD_001",
        "transaction_date": "2026-03-01T10:00:00Z",
        "transaction_type": "INTEREST",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "125.0",
        "trade_currency": "USD",
        "currency": "USD",
        "interest_direction": "INCOME",
        "withholding_tax_amount": "10.0",
        "other_interest_deductions_amount": "5.0",
        "net_interest_amount": "110.0",
    }
    model = Transaction(**payload)
    assert model.interest_direction == "INCOME"
    assert model.withholding_tax_amount == Decimal("10.0")
    assert model.other_interest_deductions_amount == Decimal("5.0")
    assert model.net_interest_amount == Decimal("110.0")


def test_transaction_model_accepts_corporate_action_synthetic_flow_fields() -> None:
    payload = {
        "transaction_id": "CA_FIELDS_001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "OLD_SEC_001",
        "security_id": "OLD_SEC_001",
        "transaction_date": "2026-03-15T10:00:00Z",
        "transaction_type": "MERGER_OUT",
        "quantity": "100.0",
        "price": "0",
        "gross_transaction_amount": "10000.0",
        "trade_currency": "USD",
        "currency": "USD",
        "parent_event_reference": "UPSTREAM-CA-REF-2026-0001",
        "child_role": "SOURCE_POSITION_CLOSE",
        "source_instrument_id": "OLD_SEC_001",
        "target_instrument_id": "NEW_SEC_001",
        "linked_cash_transaction_id": "CA-CIL-CASH-001",
        "has_synthetic_flow": True,
        "synthetic_flow_effective_date": "2026-03-15",
        "synthetic_flow_amount_local": "-10000.0",
        "synthetic_flow_currency": "USD",
        "synthetic_flow_amount_base": "-10000.0",
        "synthetic_flow_fx_rate_to_base": "1.0",
        "synthetic_flow_price_used": "100.0",
        "synthetic_flow_quantity_used": "100.0",
        "synthetic_flow_valuation_method": "MVT_PRICE_X_QTY",
        "synthetic_flow_classification": "POSITION_TRANSFER_OUT",
        "synthetic_flow_price_source": "UPSTREAM",
        "synthetic_flow_fx_source": "FX_SERVICE",
        "synthetic_flow_source": "UPSTREAM_PROVIDED",
    }
    model = Transaction(**payload)
    assert model.parent_event_reference == "UPSTREAM-CA-REF-2026-0001"
    assert model.child_role == "SOURCE_POSITION_CLOSE"
    assert model.source_instrument_id == "OLD_SEC_001"
    assert model.target_instrument_id == "NEW_SEC_001"
    assert model.linked_cash_transaction_id == "CA-CIL-CASH-001"
    assert model.has_synthetic_flow is True
    assert model.synthetic_flow_classification == "POSITION_TRANSFER_OUT"
