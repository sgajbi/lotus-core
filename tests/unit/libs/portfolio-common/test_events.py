from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.events import (
    CoreEventModel,
    TransactionEvent,
    transaction_event_ordering_key,
)
from pydantic import ValidationError


def _txn(
    transaction_id: str,
    transaction_date: datetime,
    created_at: datetime | None,
    transaction_type: str = "BUY",
    child_sequence_hint: int | None = None,
    target_instrument_id: str | None = None,
    settlement_date: object | None = None,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        quantity=Decimal("1"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        currency="USD",
        created_at=created_at,
        settlement_date=settlement_date,
        child_sequence_hint=child_sequence_hint,
        target_instrument_id=target_instrument_id,
    )


def test_transaction_event_ordering_key_is_deterministic_for_same_timestamp() -> None:
    ts = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
    later_ingest = datetime(2026, 1, 10, 8, 5, tzinfo=UTC)
    earlier_ingest = datetime(2026, 1, 10, 8, 1, tzinfo=UTC)
    txn_b = _txn("TXN_B", ts, later_ingest)
    txn_a = _txn("TXN_A", ts, earlier_ingest)

    ordered = sorted([txn_b, txn_a], key=transaction_event_ordering_key)
    assert [t.transaction_id for t in ordered] == ["TXN_A", "TXN_B"]


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


def test_transaction_event_ordering_key_handles_mixed_naive_and_aware_inputs() -> None:
    naive = _txn("TXN_NAIVE", datetime(2026, 1, 10, 8, 0), None)
    aware = _txn("TXN_AWARE", datetime(2026, 1, 10, 8, 0, tzinfo=UTC), None)

    ordered = sorted([naive, aware], key=transaction_event_ordering_key)

    assert [event.transaction_id for event in ordered] == ["TXN_AWARE", "TXN_NAIVE"]
    assert all(event.transaction_date.tzinfo == UTC for event in ordered)


def test_transaction_event_ordering_key_handles_post_validation_naive_datetime() -> None:
    mutated = _txn("TXN_MUTATED", datetime(2026, 1, 10, 8, 0, tzinfo=UTC), None)
    aware = _txn("TXN_AWARE", datetime(2026, 1, 10, 8, 0, tzinfo=UTC), None)
    mutated.transaction_date = datetime(2026, 1, 10, 8, 0)

    ordered = sorted([mutated, aware], key=transaction_event_ordering_key)

    assert [event.transaction_id for event in ordered] == ["TXN_AWARE", "TXN_MUTATED"]


def test_transaction_event_ordering_key_uses_transaction_id_as_last_tiebreak() -> None:
    ts = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
    txn_b = _txn("TXN_B", ts, None)
    txn_a = _txn("TXN_A", ts, None)

    ordered = sorted([txn_b, txn_a], key=transaction_event_ordering_key)
    assert [t.transaction_id for t in ordered] == ["TXN_A", "TXN_B"]


def test_transaction_event_ordering_key_orders_bundle_a_source_before_targets() -> None:
    ts = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
    target = _txn(
        "TXN_TARGET",
        ts,
        None,
        transaction_type="SPIN_IN",
        child_sequence_hint=2,
        target_instrument_id="TGT2",
    )
    source = _txn("TXN_SOURCE", ts, None, transaction_type="SPIN_OFF")

    ordered = sorted([target, source], key=transaction_event_ordering_key)
    assert [t.transaction_id for t in ordered] == ["TXN_SOURCE", "TXN_TARGET"]


def test_transaction_event_ordering_key_orders_bundle_a_targets_by_sequence_then_instrument() -> (
    None
):
    ts = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
    target_2 = _txn(
        "TXN_TARGET_2",
        ts,
        None,
        transaction_type="DEMERGER_IN",
        child_sequence_hint=2,
        target_instrument_id="TGT_B",
    )
    target_1 = _txn(
        "TXN_TARGET_1",
        ts,
        None,
        transaction_type="DEMERGER_IN",
        child_sequence_hint=1,
        target_instrument_id="TGT_A",
    )
    target_fallback = _txn(
        "TXN_TARGET_FALLBACK",
        ts,
        None,
        transaction_type="DEMERGER_IN",
        child_sequence_hint=None,
        target_instrument_id="TGT_AA",
    )

    ordered = sorted([target_2, target_fallback, target_1], key=transaction_event_ordering_key)
    assert [t.transaction_id for t in ordered] == [
        "TXN_TARGET_1",
        "TXN_TARGET_2",
        "TXN_TARGET_FALLBACK",
    ]


def test_transaction_event_ordering_key_orders_rights_lifecycle_dependencies() -> None:
    ts = datetime(2026, 1, 10, 8, 0, tzinfo=UTC)
    allocate = _txn("TXN_ALLOCATE", ts, None, transaction_type="RIGHTS_ALLOCATE")
    subscribe = _txn("TXN_SUBSCRIBE", ts, None, transaction_type="RIGHTS_SUBSCRIBE")
    delivery = _txn("TXN_DELIVERY", ts, None, transaction_type="RIGHTS_SHARE_DELIVERY")
    refund = _txn("TXN_REFUND", ts, None, transaction_type="RIGHTS_REFUND")

    ordered = sorted([refund, delivery, subscribe, allocate], key=transaction_event_ordering_key)
    assert [t.transaction_id for t in ordered] == [
        "TXN_ALLOCATE",
        "TXN_SUBSCRIBE",
        "TXN_DELIVERY",
        "TXN_REFUND",
    ]


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
