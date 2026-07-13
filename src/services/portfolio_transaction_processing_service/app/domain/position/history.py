"""Build deterministic position history from canonical booked transactions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from ..transaction.booked import BookedTransaction
from ..transaction.corporate_action.ordering import (
    corporate_action_dependency_rank,
    corporate_action_target_order_key,
)
from .reducer import PositionBalanceState, calculate_next_position_state

PositionTransactionOrderKey = tuple[date, datetime, int, int, str, datetime, str]


class PositionHistoryInvariantError(ValueError):
    """Report a transaction stream that cannot form one position history."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PositionHistoryRecord:
    """Represent one immutable position balance after a booked transaction."""

    portfolio_id: str
    security_id: str
    transaction_id: str
    position_date: date
    quantity: Decimal
    cost_basis: Decimal
    cost_basis_local: Decimal
    epoch: int

    @property
    def balance(self) -> PositionBalanceState:
        """Return the reducer state represented by this history record."""
        return PositionBalanceState(
            quantity=self.quantity,
            cost_basis=self.cost_basis,
            cost_basis_local=self.cost_basis_local,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PositionRecalculationState:
    """Represent the epoch and dirty-window state for one position key."""

    portfolio_id: str
    security_id: str
    epoch: int
    watermark_date: date
    status: str


def position_transaction_ordering_key(
    transaction: BookedTransaction,
) -> PositionTransactionOrderKey:
    """Return the canonical total ordering for position-history replay."""
    transaction_timestamp = _aware_datetime(transaction.transaction_date)
    ingestion_timestamp = (
        _aware_datetime(transaction.created_at)
        if transaction.created_at is not None
        else datetime.fromtimestamp(0, tz=timezone.utc)
    )
    target_sequence, target_instrument_id = corporate_action_target_order_key(transaction)
    return (
        transaction_timestamp.date(),
        transaction_timestamp,
        corporate_action_dependency_rank(transaction),
        target_sequence,
        target_instrument_id,
        ingestion_timestamp,
        transaction.transaction_id,
    )


def order_position_transactions(
    transactions: Iterable[BookedTransaction],
) -> tuple[BookedTransaction, ...]:
    """Return booked transactions in deterministic position replay order."""
    return tuple(sorted(transactions, key=position_transaction_ordering_key))


def build_position_history(
    *,
    anchor: PositionHistoryRecord | None,
    transactions: Iterable[BookedTransaction],
    epoch: int,
) -> tuple[PositionHistoryRecord, ...]:
    """Build immutable position records after an optional prior balance."""
    ordered_transactions = order_position_transactions(transactions)
    if not ordered_transactions:
        return ()
    _require_single_position_key(anchor=anchor, transactions=ordered_transactions)

    current_balance = anchor.balance if anchor is not None else PositionBalanceState()
    records: list[PositionHistoryRecord] = []
    for transaction in ordered_transactions:
        current_balance = calculate_next_position_state(current_balance, transaction)
        records.append(
            PositionHistoryRecord(
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
                transaction_id=transaction.transaction_id,
                position_date=transaction.transaction_date.date(),
                quantity=current_balance.quantity,
                cost_basis=current_balance.cost_basis,
                cost_basis_local=current_balance.cost_basis_local,
                epoch=epoch,
            )
        )
    return tuple(records)


def _require_single_position_key(
    *,
    anchor: PositionHistoryRecord | None,
    transactions: tuple[BookedTransaction, ...],
) -> None:
    expected_key = (transactions[0].portfolio_id, transactions[0].security_id)
    transaction_keys = {
        (transaction.portfolio_id, transaction.security_id) for transaction in transactions
    }
    if len(transaction_keys) != 1 or (
        anchor is not None and (anchor.portfolio_id, anchor.security_id) != expected_key
    ):
        raise PositionHistoryInvariantError(
            "Position history requires transactions and anchor for one portfolio-security key"
        )


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
