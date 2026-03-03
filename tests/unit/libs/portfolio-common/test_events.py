from datetime import UTC, datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent, transaction_event_ordering_key


def _txn(transaction_id: str, transaction_date: datetime, created_at: datetime | None) -> TransactionEvent:
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
