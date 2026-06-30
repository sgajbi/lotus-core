from datetime import datetime, timedelta, timezone
from decimal import Decimal

from cost_engine.domain.models.transaction import Transaction


def _transaction(**overrides) -> Transaction:
    payload = {
        "transaction_id": "TXN-001",
        "portfolio_id": "P1",
        "instrument_id": "AAPL",
        "security_id": "S1",
        "transaction_type": "BUY",
        "transaction_date": datetime(2026, 1, 15),
        "settlement_date": datetime(2026, 1, 17),
        "quantity": Decimal("10"),
        "gross_transaction_amount": Decimal("1500"),
        "trade_currency": "USD",
        "portfolio_base_currency": "USD",
    }
    payload.update(overrides)
    return Transaction(**payload)


def test_transaction_datetime_z_suffix_becomes_utc_aware() -> None:
    transaction = _transaction(
        transaction_date="2026-01-15T10:30:00Z",
        settlement_date="2026-01-17T10:30:00Z",
    )

    assert transaction.transaction_date == datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    assert transaction.settlement_date == datetime(2026, 1, 17, 10, 30, tzinfo=timezone.utc)


def test_transaction_naive_datetime_inputs_are_marked_utc() -> None:
    transaction = _transaction(
        transaction_date=datetime(2026, 1, 15, 10, 30),
        settlement_date="2026-01-17T10:30:00",
    )

    assert transaction.transaction_date == datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    assert transaction.settlement_date == datetime(2026, 1, 17, 10, 30, tzinfo=timezone.utc)


def test_transaction_aware_datetime_offset_is_preserved() -> None:
    singapore_time = timezone(timedelta(hours=8))

    transaction = _transaction(
        transaction_date=datetime(2026, 1, 15, 10, 30, tzinfo=singapore_time)
    )

    assert transaction.transaction_date == datetime(2026, 1, 15, 10, 30, tzinfo=singapore_time)


def test_transaction_settlement_date_can_remain_none() -> None:
    transaction = _transaction(settlement_date=None)

    assert transaction.settlement_date is None
