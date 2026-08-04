from datetime import UTC, date, datetime, timedelta, timezone
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
        "transaction_date": "2025-07-21T00:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "150.0",
        "gross_transaction_amount": "1500.0",
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": "5.0",
        "settlement_date": "2025-07-23T00:00:00Z",
        "created_at": datetime.now(UTC),
    }
    transaction = Transaction(**valid_payload)
    assert transaction.transaction_id == "test_txn_001"
    assert transaction.quantity == Decimal("10.0")
    assert transaction.transaction_date.tzinfo is not None
    assert transaction.settlement_date is not None
    assert transaction.settlement_date.tzinfo is not None
    assert transaction.created_at.tzinfo is not None


def test_transaction_model_preserves_canonical_redemption_terms() -> None:
    transaction = Transaction(
        transaction_id="RED-001",
        portfolio_id="PORT-001",
        instrument_id="BOND-001",
        security_id="BOND-001",
        transaction_date="2026-08-04T00:00:00Z",
        transaction_type="PARTIAL_REDEMPTION",
        quantity="25",
        price="100",
        gross_transaction_amount="2500",
        trade_currency="USD",
        currency="USD",
        redemption_price_type=" par ",
        old_factor="1",
        new_factor="0.75",
        principal_proceeds_local="2500",
        accrued_interest_proceeds_local="50",
        embedded_fee_amount_local="2",
        embedded_tax_amount_local="3",
    )

    assert transaction.redemption_price_type == "PAR"
    assert transaction.old_factor == Decimal("1")
    assert transaction.new_factor == Decimal("0.75")
    assert transaction.principal_proceeds_local == Decimal("2500")
    assert transaction.accrued_interest_proceeds_local == Decimal("50")


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        (" par ", "PAR"),
        ("call_price", "CALL_PRICE"),
        (" MARKET_PRICE ", "MARKET_PRICE"),
    ],
)
def test_transaction_model_accepts_governed_redemption_price_types(
    provided: str,
    expected: str,
) -> None:
    payload = {
        "transaction_id": "RED-PRICE-TYPE",
        "portfolio_id": "PORT-001",
        "instrument_id": "BOND-001",
        "security_id": "BOND-001",
        "transaction_date": "2026-08-04T00:00:00Z",
        "transaction_type": "MATURITY_REDEMPTION",
        "quantity": "25",
        "price": "100",
        "gross_transaction_amount": "2500",
        "trade_currency": "USD",
        "currency": "USD",
        "redemption_price_type": provided,
    }

    assert Transaction(**payload).redemption_price_type == expected


@pytest.mark.parametrize("provided", ["FIXED_PRICE", "CALL", "", "  "])
def test_transaction_model_rejects_unsupported_redemption_price_types(provided: str) -> None:
    payload = {
        "transaction_id": "RED-PRICE-TYPE-INVALID",
        "portfolio_id": "PORT-001",
        "instrument_id": "BOND-001",
        "security_id": "BOND-001",
        "transaction_date": "2026-08-04T00:00:00Z",
        "transaction_type": "MATURITY_REDEMPTION",
        "quantity": "25",
        "price": "100",
        "gross_transaction_amount": "2500",
        "trade_currency": "USD",
        "currency": "USD",
        "redemption_price_type": provided,
    }

    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload)

    assert exc_info.value.errors(include_input=False)[0]["loc"] == ("redemption_price_type",)


def test_transaction_model_documents_governed_redemption_price_types() -> None:
    schema = Transaction.model_json_schema()["properties"]["redemption_price_type"]
    enum_values = next(
        alternative["enum"] for alternative in schema["anyOf"] if "enum" in alternative
    )

    assert enum_values == ["PAR", "CALL_PRICE", "MARKET_PRICE"]


@pytest.mark.parametrize(
    ("old_factor", "new_factor"),
    [("1", None), (None, "0.75"), ("1", "1"), ("1", "1.01")],
)
def test_transaction_model_rejects_invalid_redemption_factor_shape(
    old_factor: str | None,
    new_factor: str | None,
) -> None:
    payload = {
        "transaction_id": "RED-INVALID",
        "portfolio_id": "PORT-001",
        "instrument_id": "BOND-001",
        "security_id": "BOND-001",
        "transaction_date": "2026-08-04T00:00:00Z",
        "transaction_type": "PARTIAL_REDEMPTION",
        "quantity": "25",
        "price": "100",
        "gross_transaction_amount": "2500",
        "trade_currency": "USD",
        "currency": "USD",
        "old_factor": old_factor,
        "new_factor": new_factor,
    }

    with pytest.raises(ValidationError, match="factor"):
        Transaction(**payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("transaction_date", "2025-07-21T00:00:00"),
        ("transaction_date", datetime(2025, 7, 21)),
        ("settlement_date", "2025-07-23T00:00:00"),
        ("settlement_date", datetime(2025, 7, 23)),
        ("created_at", "2025-07-21T00:01:00"),
        ("created_at", datetime(2025, 7, 21, 0, 1)),
        ("transaction_date", date(2025, 7, 21)),
        ("settlement_date", date(2025, 7, 23)),
        ("created_at", date(2025, 7, 21)),
    ],
)
def test_transaction_model_rejects_timezone_ambiguous_timestamps(
    field_name: str,
    value: date | datetime | str,
) -> None:
    payload = {
        "transaction_id": "test_txn_ambiguous",
        "portfolio_id": "test_port_001",
        "instrument_id": "AAPL",
        "security_id": "SEC_AAPL",
        "transaction_date": "2025-07-21T00:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "150.0",
        "gross_transaction_amount": "1500.0",
        "trade_currency": "USD",
        "currency": "USD",
        "settlement_date": "2025-07-23T00:00:00Z",
        field_name: value,
    }

    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload)

    assert exc_info.value.errors(include_input=False)[0]["loc"] == (field_name,)
    assert "timezone-aware" in str(exc_info.value)


def test_transaction_model_canonicalizes_aware_timestamps_to_utc() -> None:
    singapore = timezone(timedelta(hours=8))
    transaction = Transaction(
        transaction_id="test_txn_aware",
        portfolio_id="test_port_001",
        instrument_id="AAPL",
        security_id="SEC_AAPL",
        transaction_date=datetime(2025, 7, 21, 8, 0, tzinfo=singapore),
        transaction_type="BUY",
        quantity="10.0",
        price="150.0",
        gross_transaction_amount="1500.0",
        trade_currency="USD",
        currency="USD",
    )

    assert transaction.transaction_date == datetime(2025, 7, 21, tzinfo=UTC)


def test_transaction_model_trims_required_identity_fields() -> None:
    payload = {
        "transaction_id": " TXN_TRIM_001 ",
        "portfolio_id": " PORT_TRIM_001 ",
        "instrument_id": " INST_TRIM_001 ",
        "security_id": " SEC_TRIM_001 ",
        "transaction_date": "2025-07-21T00:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "150.0",
        "gross_transaction_amount": "1500.0",
        "trade_currency": "USD",
        "currency": "USD",
    }

    transaction = Transaction(**payload)

    assert transaction.transaction_id == "TXN_TRIM_001"
    assert transaction.portfolio_id == "PORT_TRIM_001"
    assert transaction.instrument_id == "INST_TRIM_001"
    assert transaction.security_id == "SEC_TRIM_001"


@pytest.mark.parametrize(
    "field_name",
    ["transaction_id", "portfolio_id", "instrument_id", "security_id"],
)
def test_transaction_model_rejects_blank_required_identity_fields(field_name: str) -> None:
    payload = {
        "transaction_id": "TXN_VALID_001",
        "portfolio_id": "PORT_VALID_001",
        "instrument_id": "INST_VALID_001",
        "security_id": "SEC_VALID_001",
        "transaction_date": "2025-07-21T00:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "150.0",
        "gross_transaction_amount": "1500.0",
        "trade_currency": "USD",
        "currency": "USD",
        field_name: "   ",
    }

    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload)

    assert any(
        field_name in err.get("loc", ()) and "Identifier must not be blank" in err["msg"]
        for err in exc_info.value.errors()
    )


def test_transaction_model_missing_field_fails():
    """
    Tests that the Transaction model fails validation if a required field is missing.
    """
    invalid_payload = {
        "transaction_id": "test_txn_002",
        "portfolio_id": "test_port_002",
        "security_id": "SEC_GOOG",
        "transaction_date": "2025-07-22T00:00:00Z",
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
        "transaction_date": "2025-01-01T00:00:00Z",
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
        "transaction_date": "2025-01-01T00:00:00Z",
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
        "transaction_date": "2025-01-01T00:00:00Z",
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


def test_transaction_model_rejects_negative_fee_component() -> None:
    payload = {
        "transaction_id": "txn_negative_fee_component",
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": "2025-01-01T00:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10.0",
        "price": "100.0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD",
        "brokerage": "-0.01",
    }

    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload)

    assert any("brokerage" in str(err.get("loc")) for err in exc_info.value.errors())


def test_transaction_model_non_numeric_input_fails():
    """
    Tests that the Transaction model fails validation for non-numeric input for Decimal fields.
    """
    base_payload = {
        "transaction_id": "txn_non_numeric",
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": "2025-01-01T00:00:00Z",
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
        "transaction_date": "2025-08-23T00:00:00Z",
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


def test_transaction_schema_describes_withholding_for_dividend_and_interest() -> None:
    description = Transaction.model_json_schema()["properties"]["withholding_tax_amount"][
        "description"
    ]

    assert "DIVIDEND or INTEREST" in description
    assert "jurisdiction-specific tax policy" in description


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
        "target_transaction_reference": "MERGER-IN-001",
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


def _destination_payload(
    transaction_type: str,
    **destination: object,
) -> dict[str, object]:
    return {
        "transaction_id": f"{transaction_type}-DESTINATION-001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "OLD_SEC_001",
        "security_id": "OLD_SEC_001",
        "transaction_date": "2026-03-15T10:00:00Z",
        "transaction_type": transaction_type,
        "quantity": "100.0",
        "price": "1.0",
        "gross_transaction_amount": "100.0",
        "trade_currency": "USD",
        "currency": "USD",
        **destination,
    }


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        (
            {
                "target_transaction_reference": " TRANSFER-IN-001 ",
                "target_instrument_id": " NEW_SEC_001 ",
            },
            ("TRANSFER-IN-001", "NEW_SEC_001", None),
        ),
        (
            {"external_destination_reference": " CUSTODIAN-ACCOUNT-7788 "},
            (None, None, "CUSTODIAN-ACCOUNT-7788"),
        ),
    ],
)
def test_transfer_out_accepts_exactly_one_complete_destination(
    destination: dict[str, object],
    expected: tuple[str | None, str | None, str | None],
) -> None:
    transaction = Transaction(**_destination_payload("TRANSFER_OUT", **destination))

    assert (
        transaction.target_transaction_reference,
        transaction.target_instrument_id,
        transaction.external_destination_reference,
    ) == expected


@pytest.mark.parametrize(
    "destination",
    [
        {},
        {"target_transaction_reference": "TRANSFER-IN-001"},
        {"target_instrument_id": "NEW_SEC_001"},
        {"external_destination_reference": "   "},
        {
            "target_transaction_reference": "TRANSFER-IN-001",
            "target_instrument_id": "NEW_SEC_001",
            "external_destination_reference": "CUSTODIAN-ACCOUNT-7788",
        },
    ],
)
def test_transfer_out_rejects_missing_partial_or_ambiguous_destination(
    destination: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="exactly one complete destination"):
        Transaction(**_destination_payload("TRANSFER_OUT", **destination))


@pytest.mark.parametrize(
    ("transaction_type", "destination"),
    [
        ("BUY", {"target_transaction_reference": "TRANSFER-IN-001"}),
        ("BUY", {"target_instrument_id": "NEW_SEC_001"}),
        ("MATURITY_REDEMPTION", {"external_destination_reference": "CUSTODIAN-7788"}),
        ("MERGER_OUT", {"external_destination_reference": "CUSTODIAN-7788"}),
    ],
)
def test_non_transfer_destination_metadata_is_rejected(
    transaction_type: str,
    destination: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="destination"):
        Transaction(**_destination_payload(transaction_type, **destination))


@pytest.mark.parametrize(
    ("transaction_type", "target_transaction_reference"),
    [
        ("MERGER_OUT", "MERGER-IN-001"),
        ("EXCHANGE_OUT", "EXCHANGE-IN-001"),
        ("REPLACEMENT_OUT", "REPLACEMENT-IN-001"),
    ],
)
def test_internal_lot_disposal_accepts_complete_target_metadata(
    transaction_type: str,
    target_transaction_reference: str,
) -> None:
    transaction = Transaction(
        **_destination_payload(
            transaction_type,
            target_transaction_reference=f" {target_transaction_reference} ",
            target_instrument_id=" NEW_SEC_001 ",
        )
    )

    assert transaction.target_transaction_reference == target_transaction_reference
    assert transaction.target_instrument_id == "NEW_SEC_001"


@pytest.mark.parametrize("transaction_type", ["MERGER_OUT", "EXCHANGE_OUT", "REPLACEMENT_OUT"])
@pytest.mark.parametrize(
    "destination",
    [
        {},
        {"target_transaction_reference": "TARGET-IN-001"},
        {"target_instrument_id": "NEW_SEC_001"},
        {
            "target_transaction_reference": "   ",
            "target_instrument_id": "NEW_SEC_001",
        },
    ],
)
def test_internal_lot_disposal_rejects_missing_or_partial_target_metadata(
    transaction_type: str,
    destination: dict[str, object],
) -> None:
    with pytest.raises(
        ValidationError,
        match="requires target_transaction_reference and target_instrument_id",
    ):
        Transaction(**_destination_payload(transaction_type, **destination))


@pytest.mark.parametrize("transaction_type", ["SPIN_OFF", "DEMERGER_OUT"])
def test_partial_basis_transfer_does_not_over_require_disposal_destination(
    transaction_type: str,
) -> None:
    transaction = Transaction(**_destination_payload(transaction_type))

    assert transaction.target_transaction_reference is None
    assert transaction.target_instrument_id is None


@pytest.mark.parametrize(
    "field_name",
    ["allocated_cost_basis_local", "allocated_cost_basis_base"],
)
def test_transaction_model_rejects_negative_allocated_cash_basis(field_name: str) -> None:
    payload = {
        "transaction_id": "CA_CASH_BASIS_NEGATIVE_001",
        "portfolio_id": "PORT_META_001",
        "instrument_id": "OLD_SEC_001",
        "security_id": "OLD_SEC_001",
        "transaction_date": "2026-03-15T10:00:00Z",
        "transaction_type": "CASH_CONSIDERATION",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "250.0",
        "trade_currency": "USD",
        "currency": "USD",
        field_name: "-0.01",
    }

    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload)

    assert any(field_name in error["loc"] for error in exc_info.value.errors())


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("price", "1.00000000001"),
        ("gross_transaction_amount", "100000000"),
        ("realized_fx_pnl_base", "1.00000000001"),
        ("synthetic_flow_fx_rate_to_base", "1.00000000001"),
    ],
)
def test_transaction_model_rejects_values_not_exactly_persistable(
    field_name: str,
    invalid_value: str,
) -> None:
    payload = {
        "transaction_id": "TXN_PRECISION_REJECT_001",
        "portfolio_id": "PORT_PRECISION_001",
        "instrument_id": "SEC_PRECISION_001",
        "security_id": "SEC_PRECISION_001",
        "transaction_date": "2026-07-28T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": "1",
        "price": "1",
        "gross_transaction_amount": "1",
        "trade_currency": "USD",
        "currency": "USD",
        field_name: invalid_value,
    }

    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload)

    matching_errors = [
        error for error in exc_info.value.errors() if field_name in error.get("loc", ())
    ]
    assert len(matching_errors) == 1
    assert "transaction-persistence-v1" in matching_errors[0]["msg"]


def test_transaction_model_rejects_aggregated_fee_overflow() -> None:
    payload = {
        "transaction_id": "TXN_FEE_PRECISION_REJECT_001",
        "portfolio_id": "PORT_PRECISION_001",
        "instrument_id": "SEC_PRECISION_001",
        "security_id": "SEC_PRECISION_001",
        "transaction_date": "2026-07-28T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": "1",
        "price": "1",
        "gross_transaction_amount": "1",
        "trade_currency": "USD",
        "currency": "USD",
        "brokerage": "60000000",
        "stamp_duty": "60000000",
    }

    with pytest.raises(ValidationError, match="transaction-persistence-v1"):
        Transaction(**payload)
