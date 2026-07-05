import json
from decimal import Decimal
from unittest.mock import MagicMock

from portfolio_common.events import TransactionEvent

from src.services.persistence_service.app.adapters.persistence_event_adapter import (
    decode_persistence_message_payload,
    validate_persistence_event_payload,
)


def _message(payload: dict[str, object], *, offset: int) -> MagicMock:
    msg = MagicMock()
    msg.topic.return_value = "transactions.persisted"
    msg.partition.return_value = 0
    msg.offset.return_value = offset
    msg.value.return_value = json.dumps(payload).encode("utf-8")
    return msg


def _transaction_payload() -> dict[str, object]:
    return {
        "transaction_id": "TXN-SEMANTIC-DUPLICATE-001",
        "portfolio_id": "PORT-SEMANTIC-DUPLICATE",
        "instrument_id": "INST-SEMANTIC-DUPLICATE",
        "security_id": "SEC-SEMANTIC-DUPLICATE",
        "transaction_date": "2026-04-10T09:00:00Z",
        "transaction_type": "BUY",
        "quantity": "10",
        "price": "101.25",
        "gross_transaction_amount": "1012.50",
        "trade_currency": "USD",
        "currency": "USD",
    }


def test_persistence_event_idempotency_key_is_semantic_across_transport_offsets() -> None:
    first_payload = decode_persistence_message_payload(_message(_transaction_payload(), offset=41))
    redelivered_payload = decode_persistence_message_payload(
        _message(_transaction_payload(), offset=42)
    )

    first = validate_persistence_event_payload(first_payload, TransactionEvent)
    redelivered = validate_persistence_event_payload(redelivered_payload, TransactionEvent)

    assert first.event_id == "transactions.persisted-0-41"
    assert redelivered.event_id == "transactions.persisted-0-42"
    assert first.idempotency_key == redelivered.idempotency_key
    assert first.idempotency_key == "TXN-SEMANTIC-DUPLICATE-001"
    assert first.event.quantity == Decimal("10")
