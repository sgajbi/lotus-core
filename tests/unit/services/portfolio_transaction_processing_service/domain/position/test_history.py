"""Test deterministic position-history domain construction."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.position.history import (
    PositionHistoryInvariantError,
    PositionHistoryRecord,
    PositionRecalculationState,
    build_position_history,
    order_position_transactions,
)

REPO_ROOT = Path(__file__).resolve().parents[6]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
TARGET_TEST = SERVICE_TEST_ROOT / "domain/position/test_history.py"
RETIRED_TEST = SERVICE_TEST_ROOT / "position/test_position_history_domain.py"


def test_position_history_tests_are_owned_by_domain_boundary() -> None:
    assert Path(__file__).resolve() == TARGET_TEST.resolve()
    assert not RETIRED_TEST.exists()
    assert list((SERVICE_TEST_ROOT / "position").glob("*.py")) == []


def _transaction(
    transaction_id: str,
    transaction_type: str,
    *,
    transaction_date: datetime | None = None,
    quantity: Decimal = Decimal("0"),
    net_cost: Decimal | None = None,
    net_cost_local: Decimal | None = None,
    child_sequence_hint: int | None = None,
    target_instrument_id: str | None = None,
    created_at: datetime | None = None,
    portfolio_id: str = "PB-001",
    security_id: str = "SEC-001",
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=transaction_date or datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=quantity,
        price=Decimal("10"),
        gross_transaction_amount=abs(quantity * Decimal("10")),
        trade_currency="SGD",
        currency="SGD",
        net_cost=net_cost,
        net_cost_local=net_cost_local,
        child_sequence_hint=child_sequence_hint,
        target_instrument_id=target_instrument_id,
        created_at=created_at,
    )


def test_order_position_transactions_uses_canonical_dependency_and_target_order() -> None:
    transaction_time = datetime(2026, 4, 10, 9, 30)
    transactions = (
        _transaction("CASH", "CASH_CONSIDERATION", transaction_date=transaction_time),
        _transaction(
            "TARGET-2",
            "DEMERGER_IN",
            transaction_date=transaction_time,
            child_sequence_hint=2,
            target_instrument_id="SEC-C",
        ),
        _transaction("SOURCE", "DEMERGER_OUT", transaction_date=transaction_time),
        _transaction(
            "TARGET-1B",
            "DEMERGER_IN",
            transaction_date=transaction_time,
            child_sequence_hint=1,
            target_instrument_id="SEC-B",
        ),
        _transaction(
            "TARGET-1A",
            "DEMERGER_IN",
            transaction_date=transaction_time,
            child_sequence_hint=1,
            target_instrument_id="SEC-A",
        ),
    )

    ordered = order_position_transactions(transactions)

    assert tuple(transaction.transaction_id for transaction in ordered) == (
        "SOURCE",
        "TARGET-1A",
        "TARGET-1B",
        "TARGET-2",
        "CASH",
    )


def test_order_position_transactions_uses_ingestion_and_identity_tiebreakers() -> None:
    transaction_time = datetime(2026, 4, 10, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    transactions = (
        _transaction(
            "TX-B",
            "BUY",
            transaction_date=transaction_time,
            created_at=datetime(2026, 4, 10, 2, 0, tzinfo=timezone.utc),
        ),
        _transaction(
            "TX-C",
            "BUY",
            transaction_date=transaction_time,
            created_at=datetime(2026, 4, 10, 1, 0, tzinfo=timezone.utc),
        ),
        _transaction(
            "TX-A",
            "BUY",
            transaction_date=transaction_time,
            created_at=datetime(2026, 4, 10, 1, 0, tzinfo=timezone.utc),
        ),
    )

    ordered = order_position_transactions(transactions)

    assert tuple(transaction.transaction_id for transaction in ordered) == (
        "TX-A",
        "TX-C",
        "TX-B",
    )


def test_build_position_history_applies_anchor_and_returns_immutable_records() -> None:
    anchor = PositionHistoryRecord(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-ANCHOR",
        position_date=date(2026, 4, 9),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("95"),
        epoch=3,
    )
    buy = _transaction(
        "TX-BUY",
        "BUY",
        quantity=Decimal("5"),
        net_cost=Decimal("60"),
        net_cost_local=Decimal("55"),
    )
    sell = _transaction(
        "TX-SELL",
        "SELL",
        transaction_date=datetime(2026, 4, 11, 9, 30, tzinfo=timezone.utc),
        quantity=Decimal("3"),
        net_cost=Decimal("-24"),
        net_cost_local=Decimal("-21"),
    )

    records = build_position_history(anchor=anchor, transactions=(sell, buy), epoch=4)

    assert records == (
        PositionHistoryRecord(
            portfolio_id="PB-001",
            security_id="SEC-001",
            transaction_id="TX-BUY",
            position_date=date(2026, 4, 10),
            quantity=Decimal("15"),
            cost_basis=Decimal("160"),
            cost_basis_local=Decimal("150"),
            epoch=4,
        ),
        PositionHistoryRecord(
            portfolio_id="PB-001",
            security_id="SEC-001",
            transaction_id="TX-SELL",
            position_date=date(2026, 4, 11),
            quantity=Decimal("12"),
            cost_basis=Decimal("136"),
            cost_basis_local=Decimal("129"),
            epoch=4,
        ),
    )
    with pytest.raises(FrozenInstanceError):
        records[0].quantity = Decimal("999")  # type: ignore[misc]


def test_build_position_history_rejects_mixed_position_keys() -> None:
    transactions = (
        _transaction("TX-001", "BUY", quantity=Decimal("1")),
        _transaction(
            "TX-002",
            "BUY",
            quantity=Decimal("1"),
            security_id="SEC-OTHER",
        ),
    )

    with pytest.raises(PositionHistoryInvariantError, match="one portfolio-security key"):
        build_position_history(anchor=None, transactions=transactions, epoch=0)


def test_position_recalculation_state_is_immutable() -> None:
    state = PositionRecalculationState(
        portfolio_id="PB-001",
        security_id="SEC-001",
        epoch=4,
        watermark_date=date(2026, 4, 9),
        status="REPROCESSING",
    )

    with pytest.raises(FrozenInstanceError):
        state.epoch = 5  # type: ignore[misc]
