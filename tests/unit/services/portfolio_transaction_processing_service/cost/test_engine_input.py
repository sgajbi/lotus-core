"""Verify domain mapping from booked transactions to cost-basis engine inputs."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    build_cost_basis_engine_input,
    normalize_cost_fee_amount,
)


class _StringCountedAmount:
    """Record string normalization calls for one fee value."""

    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


def _transaction(**overrides: object) -> BookedTransaction:
    values = {
        "transaction_id": "BUY-ENGINE-INPUT-001",
        "portfolio_id": "PB-SG-001",
        "instrument_id": "INST-001",
        "security_id": "SEC-001",
        "transaction_date": datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        "transaction_type": "BUY",
        "quantity": Decimal("10"),
        "price": Decimal("25.50"),
        "gross_transaction_amount": Decimal("255.00"),
        "trade_currency": "SGD",
        "currency": "SGD",
    }
    values.update(overrides)
    return BookedTransaction(**values)  # type: ignore[arg-type]


def test_positive_trade_fee_maps_to_brokerage_when_components_are_absent() -> None:
    engine_input = build_cost_basis_engine_input(_transaction(trade_fee=Decimal("7.50")))

    assert engine_input["trade_fee"] == "7.50"
    assert engine_input["fees"] == {"brokerage": "7.50"}


def test_explicit_fee_components_determine_trade_fee() -> None:
    engine_input = build_cost_basis_engine_input(
        _transaction(
            trade_fee=Decimal("99"),
            brokerage=Decimal("4.25"),
            stamp_duty=Decimal("1.75"),
        )
    )

    assert engine_input["trade_fee"] == "6.00"
    assert engine_input["fees"] == {
        "brokerage": "4.25",
        "stamp_duty": "1.75",
        "exchange_fee": "0",
        "gst": "0",
        "other_fees": "0",
    }


@pytest.mark.parametrize(
    ("overrides", "field_name"),
    [
        ({"trade_fee": Decimal("-0.01")}, "trade_fee"),
        ({"brokerage": Decimal("-0.01")}, "brokerage"),
    ],
)
def test_negative_fee_amount_is_rejected(
    overrides: dict[str, object],
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        build_cost_basis_engine_input(_transaction(**overrides))


def test_typed_corporate_action_metadata_is_preserved() -> None:
    engine_input = build_cost_basis_engine_input(
        _transaction(
            synthetic_flow_effective_date=date(2026, 7, 5),
            synthetic_flow_amount_local=Decimal("-1200"),
            synthetic_flow_amount_base=Decimal("-1450"),
        )
    )

    assert engine_input["synthetic_flow_effective_date"] == date(2026, 7, 5)
    assert engine_input["synthetic_flow_amount_local"] == Decimal("-1200")
    assert engine_input["synthetic_flow_amount_base"] == Decimal("-1450")


def test_delivery_envelope_fields_are_not_engine_inputs() -> None:
    engine_input = build_cost_basis_engine_input(_transaction())

    assert "event_type" not in engine_input
    assert "schema_version" not in engine_input
    assert "correlation_id" not in engine_input
    assert "traceparent" not in engine_input


def test_fee_amount_normalizer_converts_one_time() -> None:
    amount = _StringCountedAmount("2.50")

    assert normalize_cost_fee_amount(amount, field_name="brokerage") == Decimal("2.50")
    assert normalize_cost_fee_amount(" ", field_name="stamp_duty") == Decimal("0")
    assert amount.string_call_count == 1
