from datetime import UTC, datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent, transaction_event_ordering_key


def _txn(
    transaction_id: str,
    transaction_date: datetime,
    created_at: datetime | None,
    transaction_type: str = "BUY",
    child_sequence_hint: int | None = None,
    target_instrument_id: str | None = None,
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


def test_transaction_event_ordering_key_orders_bundle_a_targets_by_sequence_then_instrument(
) -> None:
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
