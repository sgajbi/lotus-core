"""Build deterministic position history from canonical booked transactions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)

from ..transaction.booked import BookedTransaction
from ..transaction.corporate_action.ordering import (
    corporate_action_dependency_rank,
    corporate_action_target_order_key,
    same_time_restatement_order_key,
)
from ..transaction.processing_type import resolve_effective_processing_transaction_type
from .numeric_policy import POSITION_HISTORY_LEDGER_OUTPUT_V1
from .reducer import PositionBalanceState, calculate_next_position_state

PositionTransactionOrderKey = tuple[
    date,
    datetime,
    int,
    int,
    str,
    Decimal,
    str,
    datetime,
    str,
]


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
    calculation_lineage: CalculationLineage | None = None

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
    transaction_timestamp = _canonical_ordering_datetime(
        transaction.transaction_date,
        field_name="transaction_date",
    )
    ingestion_timestamp = (
        _canonical_ordering_datetime(transaction.created_at, field_name="created_at")
        if transaction.created_at is not None
        else datetime.fromtimestamp(0, tz=timezone.utc)
    )
    target_sequence, target_instrument_id = corporate_action_target_order_key(transaction)
    restatement_order = same_time_restatement_order_key(
        transaction,
        quantity=transaction.quantity,
    ) or (Decimal(0), "")
    return (
        transaction_timestamp.date(),
        transaction_timestamp,
        corporate_action_dependency_rank(transaction),
        target_sequence,
        target_instrument_id,
        *restatement_order,
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
    prior_lineage = anchor.calculation_lineage if anchor is not None else None
    records: list[PositionHistoryRecord] = []
    for transaction in ordered_transactions:
        transaction_timestamp = _canonical_ordering_datetime(
            transaction.transaction_date,
            field_name="transaction_date",
        )
        position_date = transaction_timestamp.date()
        previous_balance = current_balance
        current_balance = calculate_next_position_state(previous_balance, transaction)
        output_payload = {
            "cost_basis": current_balance.cost_basis,
            "cost_basis_local": current_balance.cost_basis_local,
            "epoch": epoch,
            "portfolio_id": transaction.portfolio_id,
            "position_date": position_date,
            "quantity": current_balance.quantity,
            "security_id": transaction.security_id,
            "transaction_id": transaction.transaction_id,
        }
        calculation_lineage = build_calculation_lineage(
            algorithm_id="position-history-state-transition",
            algorithm_version=1,
            intermediate_precision=POSITION_HISTORY_LEDGER_OUTPUT_V1.working_precision,
            input_payload=_position_history_lineage_input(
                previous_balance=previous_balance,
                prior_lineage=prior_lineage,
                transaction=transaction,
                epoch=epoch,
            ),
            output_payload=output_payload,
            numeric_output_policy=POSITION_HISTORY_LEDGER_OUTPUT_V1.lineage_identity(),
        )
        record = PositionHistoryRecord(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            transaction_id=transaction.transaction_id,
            position_date=position_date,
            quantity=current_balance.quantity,
            cost_basis=current_balance.cost_basis,
            cost_basis_local=current_balance.cost_basis_local,
            epoch=epoch,
            calculation_lineage=calculation_lineage,
        )
        records.append(record)
        prior_lineage = calculation_lineage
    return tuple(records)


def _position_history_lineage_input(
    *,
    previous_balance: PositionBalanceState,
    prior_lineage: CalculationLineage | None,
    transaction: BookedTransaction,
    epoch: int,
) -> dict[str, object]:
    """Return the ordered source facts that can change a position-history balance."""

    return {
        "epoch": epoch,
        "previous_balance": {
            "cost_basis": previous_balance.cost_basis,
            "cost_basis_local": previous_balance.cost_basis_local,
            "quantity": previous_balance.quantity,
        },
        "prior_calculation_lineage": (
            prior_lineage.lineage_payload() if prior_lineage is not None else None
        ),
        "transaction": {
            "booked_transaction_type": transaction.transaction_type,
            "calculation_lineage": (
                transaction.calculation_lineage.lineage_payload()
                if transaction.calculation_lineage is not None
                else None
            ),
            "component_type": transaction.component_type,
            "effective_processing_transaction_type": (
                resolve_effective_processing_transaction_type(transaction)
            ),
            "gross_transaction_amount": transaction.gross_transaction_amount,
            "movement_direction": transaction.movement_direction,
            "net_cost": transaction.net_cost,
            "net_cost_local": transaction.net_cost_local,
            "ordering_key": position_transaction_ordering_key(transaction),
            "portfolio_id": transaction.portfolio_id,
            "quantity": transaction.quantity,
            "security_id": transaction.security_id,
            "transaction_id": transaction.transaction_id,
        },
    }


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


def _canonical_ordering_datetime(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PositionHistoryInvariantError(
            f"Position-history {field_name} must be timezone-aware."
        )
    return value.astimezone(timezone.utc)
