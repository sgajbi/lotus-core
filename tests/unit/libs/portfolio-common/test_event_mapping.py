import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from portfolio_common.event_mapping import (
    EventContractValidationError,
    decode_kafka_event_payload,
    kafka_event_id,
    outbox_event_payload,
    validate_kafka_event_payload,
)
from portfolio_common.events import GOVERNED_EVENT_SCHEMA_VERSION, TransactionEvent
from pydantic import ValidationError


def _message(payload: dict | bytes) -> MagicMock:
    msg = MagicMock()
    msg.topic.return_value = "transactions.raw.received"
    msg.partition.return_value = 3
    msg.offset.return_value = 17
    if isinstance(payload, bytes):
        msg.value.return_value = payload
    else:
        msg.value.return_value = json.dumps(payload).encode("utf-8")
    return msg


def test_decode_kafka_event_payload_derives_transport_identity() -> None:
    decoded = decode_kafka_event_payload(_message({"schema_version": "transaction.raw.v1"}))

    assert decoded.event_id == "transactions.raw.received-3-17"
    assert decoded.data == {"schema_version": "transaction.raw.v1"}
    assert kafka_event_id(_message({})) == "transactions.raw.received-3-17"


def test_decode_kafka_event_payload_rejects_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        decode_kafka_event_payload(_message(b"{not-json"))


def test_validate_kafka_event_payload_preserves_decimal_dates_and_lineage() -> None:
    decoded = decode_kafka_event_payload(
        _message(
            {
                "transaction_id": "TXN-EVENT-MAP-001",
                "portfolio_id": "PORT-EVENT-MAP",
                "instrument_id": "INST-EVENT-MAP",
                "security_id": "SEC-EVENT-MAP",
                "transaction_date": "2026-03-25T09:30:00Z",
                "transaction_type": "BUY",
                "quantity": "100.0000000000",
                "price": "150.0550000000",
                "gross_transaction_amount": "15005.5000000000",
                "trade_currency": "USD",
                "currency": "USD",
                "event_type": "ProcessedTransactionPersisted",
                "schema_version": GOVERNED_EVENT_SCHEMA_VERSION,
                "correlation_id": "corr-event-map",
            }
        )
    )

    event = validate_kafka_event_payload(
        decoded,
        TransactionEvent,
        expected_event_type="ProcessedTransactionPersisted",
    )

    assert event.quantity == Decimal("100.0000000000")
    assert event.transaction_date == datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    assert event.event_type == "ProcessedTransactionPersisted"
    assert event.schema_version == GOVERNED_EVENT_SCHEMA_VERSION
    assert event.correlation_id == "corr-event-map"


def test_validate_kafka_event_payload_rejects_missing_event_type_for_governed_consumer() -> None:
    decoded = decode_kafka_event_payload(
        _message(
            {
                "transaction_id": "TXN-EVENT-MAP-STRICT-001",
                "portfolio_id": "PORT-EVENT-MAP",
                "instrument_id": "INST-EVENT-MAP",
                "security_id": "SEC-EVENT-MAP",
                "transaction_date": "2026-03-25T09:30:00Z",
                "transaction_type": "BUY",
                "quantity": "100",
                "price": "150",
                "gross_transaction_amount": "15000",
                "trade_currency": "USD",
                "currency": "USD",
                "schema_version": GOVERNED_EVENT_SCHEMA_VERSION,
            }
        )
    )

    with pytest.raises(EventContractValidationError, match="event_type is required"):
        validate_kafka_event_payload(
            decoded,
            TransactionEvent,
            expected_event_type="ProcessedTransactionPersisted",
        )


def test_validate_kafka_event_payload_rejects_missing_schema_version_for_governed_consumer() -> (
    None
):
    decoded = decode_kafka_event_payload(
        _message(
            {
                "transaction_id": "TXN-EVENT-MAP-STRICT-002",
                "portfolio_id": "PORT-EVENT-MAP",
                "instrument_id": "INST-EVENT-MAP",
                "security_id": "SEC-EVENT-MAP",
                "transaction_date": "2026-03-25T09:30:00Z",
                "transaction_type": "BUY",
                "quantity": "100",
                "price": "150",
                "gross_transaction_amount": "15000",
                "trade_currency": "USD",
                "currency": "USD",
                "event_type": "ProcessedTransactionPersisted",
            }
        )
    )

    with pytest.raises(EventContractValidationError, match="schema_version is required"):
        validate_kafka_event_payload(
            decoded,
            TransactionEvent,
            expected_event_type="ProcessedTransactionPersisted",
        )


def test_validate_kafka_event_payload_rejects_unsupported_schema_version() -> None:
    decoded = decode_kafka_event_payload(
        _message(
            {
                "transaction_id": "TXN-EVENT-MAP-STRICT-003",
                "portfolio_id": "PORT-EVENT-MAP",
                "instrument_id": "INST-EVENT-MAP",
                "security_id": "SEC-EVENT-MAP",
                "transaction_date": "2026-03-25T09:30:00Z",
                "transaction_type": "BUY",
                "quantity": "100",
                "price": "150",
                "gross_transaction_amount": "15000",
                "trade_currency": "USD",
                "currency": "USD",
                "event_type": "ProcessedTransactionPersisted",
                "schema_version": "2.0.0",
            }
        )
    )

    with pytest.raises(EventContractValidationError, match="schema_version '2.0.0'"):
        validate_kafka_event_payload(
            decoded,
            TransactionEvent,
            expected_event_type="ProcessedTransactionPersisted",
        )


def test_validate_kafka_event_payload_rejects_event_type_drift() -> None:
    decoded = decode_kafka_event_payload(
        _message(
            {
                "transaction_id": "TXN-EVENT-MAP-STRICT-004",
                "portfolio_id": "PORT-EVENT-MAP",
                "instrument_id": "INST-EVENT-MAP",
                "security_id": "SEC-EVENT-MAP",
                "transaction_date": "2026-03-25T09:30:00Z",
                "transaction_type": "BUY",
                "quantity": "100",
                "price": "150",
                "gross_transaction_amount": "15000",
                "trade_currency": "USD",
                "currency": "USD",
                "event_type": "RawTransactionPersisted",
                "schema_version": GOVERNED_EVENT_SCHEMA_VERSION,
            }
        )
    )

    with pytest.raises(EventContractValidationError, match="does not match expected"):
        validate_kafka_event_payload(
            decoded,
            TransactionEvent,
            expected_event_type="ProcessedTransactionPersisted",
        )


def test_validate_kafka_event_payload_rejects_unknown_fields() -> None:
    decoded = decode_kafka_event_payload(
        _message(
            {
                "transaction_id": "TXN-EVENT-MAP-002",
                "portfolio_id": "PORT-EVENT-MAP",
                "instrument_id": "INST-EVENT-MAP",
                "security_id": "SEC-EVENT-MAP",
                "transaction_date": "2026-03-25T09:30:00Z",
                "transaction_type": "BUY",
                "quantity": "100.0000000000",
                "price": "150.0550000000",
                "gross_transaction_amount": "15005.5000000000",
                "trade_currency": "USD",
                "currency": "USD",
                "unexpected_transport_field": "reject",
            }
        )
    )

    with pytest.raises(ValidationError):
        validate_kafka_event_payload(decoded, TransactionEvent)


def test_outbox_event_payload_preserves_schema_correlation_and_json_safe_values() -> None:
    event = TransactionEvent(
        transaction_id="TXN-EVENT-MAP-003",
        portfolio_id="PORT-EVENT-MAP",
        instrument_id="INST-EVENT-MAP",
        security_id="SEC-EVENT-MAP",
        transaction_date="2026-03-25T09:30:00Z",
        transaction_type="BUY",
        quantity=Decimal("100.0000000000"),
        price=Decimal("150.0550000000"),
        gross_transaction_amount=Decimal("15005.5000000000"),
        trade_currency="USD",
        currency="USD",
        event_type="transaction.raw.received",
        schema_version="transaction.raw.v1",
        correlation_id="corr-event-map",
    )

    payload = outbox_event_payload(event)

    assert payload["transaction_date"] == "2026-03-25T09:30:00Z"
    assert payload["quantity"] == "100.0000000000"
    assert payload["event_type"] == "transaction.raw.received"
    assert payload["schema_version"] == "transaction.raw.v1"
    assert payload["correlation_id"] == "corr-event-map"
