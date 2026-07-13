from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.events import CoreEventModel, TransactionEvent
from pydantic import ValidationError


def _txn(
    transaction_id: str,
    transaction_date: datetime,
    created_at: datetime | None,
    settlement_date: object | None = None,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=transaction_date,
        transaction_type="BUY",
        quantity=Decimal("1"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        currency="USD",
        created_at=created_at,
        settlement_date=settlement_date,
    )


def test_transaction_event_standardizes_temporal_fields_to_utc_aware() -> None:
    event = _txn(
        "TXN_TIME",
        datetime(2026, 1, 10, 8, 0),
        datetime(2026, 1, 10, 8, 5),
        settlement_date="2026-01-12T10:00:00Z",
    )

    assert event.transaction_date.tzinfo == UTC
    assert event.created_at is not None
    assert event.created_at.tzinfo == UTC
    assert event.settlement_date is not None
    assert event.settlement_date.tzinfo == UTC


def test_transaction_event_rejects_unknown_payload_fields() -> None:
    payload = _txn("TXN_DRIFT", datetime(2026, 1, 10, 8, 0, tzinfo=UTC), None).model_dump()
    payload["event_version"] = "vNext"

    with pytest.raises(ValidationError) as exc_info:
        TransactionEvent.model_validate(payload)

    errors = exc_info.value.errors(include_input=False)
    assert errors == [
        {
            "type": "extra_forbidden",
            "loc": ("event_version",),
            "msg": "Extra inputs are not permitted",
            "url": "https://errors.pydantic.dev/2.13/v/extra_forbidden",
        }
    ]
    assert "vNext" not in str(errors)


def test_all_core_event_models_reject_unknown_payload_fields() -> None:
    event_models = [
        model_cls
        for model_cls in CoreEventModel.__subclasses__()
        if model_cls is not CoreEventModel
    ]

    assert event_models
    for model_cls in event_models:
        with pytest.raises(ValidationError) as exc_info:
            model_cls.model_validate({"unexpected_contract_drift": "lineage-lost"})

        errors = exc_info.value.errors(include_input=False)
        assert {
            "type": "extra_forbidden",
            "loc": ("unexpected_contract_drift",),
            "msg": "Extra inputs are not permitted",
            "url": "https://errors.pydantic.dev/2.13/v/extra_forbidden",
        } in errors
        assert "lineage-lost" not in str(errors)


def test_transaction_event_accepts_governed_envelope_metadata() -> None:
    payload = _txn("TXN_ENVELOPE", datetime(2026, 1, 10, 8, 0, tzinfo=UTC), None).model_dump()
    payload.update(
        {
            "event_type": "TransactionPersisted",
            "schema_version": "1.0.0",
            "correlation_id": "corr-transaction-envelope",
            "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        }
    )

    event = TransactionEvent.model_validate(payload)

    assert event.event_type == "TransactionPersisted"
    assert event.schema_version == "1.0.0"
    assert event.correlation_id == "corr-transaction-envelope"
    assert event.traceparent == "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
