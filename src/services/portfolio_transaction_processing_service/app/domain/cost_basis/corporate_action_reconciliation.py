"""Reconcile basis conservation across linked corporate-action transactions."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

from ..transaction import BookedTransaction
from ..transaction.corporate_action import is_bundle_a_corporate_action
from ..transaction.corporate_action.classification import (
    CASH_CONSIDERATION_TRANSACTION_TYPE,
    SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES,
    TARGET_BASIS_TRANSFER_TRANSACTION_TYPES,
    normalize_corporate_action_transaction_type,
)

DEFAULT_CORPORATE_ACTION_BASIS_TOLERANCE = Decimal("0.01")


class CorporateActionBasisReconciliationStatus(StrEnum):
    """Classify completeness and conservation of one corporate-action group."""

    BALANCED = "balanced"
    BASIS_MISMATCH = "basis_mismatch"
    INSUFFICIENT_CASH_BASIS = "insufficient_cash_basis"
    INSUFFICIENT_LEGS = "insufficient_legs"


@dataclass(frozen=True, slots=True)
class CorporateActionBasisReconciliation:
    """Summarize basis conservation for one linked corporate-action group."""

    status: CorporateActionBasisReconciliationStatus
    source_leg_count: int
    target_leg_count: int
    cash_consideration_count: int
    source_basis_out_local: Decimal
    target_basis_in_local: Decimal
    cash_basis_local: Decimal
    missing_cash_basis_count: int
    net_basis_delta_local: Decimal
    basis_tolerance: Decimal


@dataclass(slots=True)
class _BasisTotals:
    source_leg_count: int = 0
    target_leg_count: int = 0
    cash_consideration_count: int = 0
    source_basis_out_local: Decimal = Decimal(0)
    target_basis_in_local: Decimal = Decimal(0)
    cash_basis_local: Decimal = Decimal(0)
    missing_cash_basis_count: int = 0


def reconcile_corporate_action_basis(
    transactions: Iterable[BookedTransaction],
    *,
    basis_tolerance: Decimal = DEFAULT_CORPORATE_ACTION_BASIS_TOLERANCE,
) -> CorporateActionBasisReconciliation:
    """Evaluate source, target, and cash basis conservation for a linked group."""

    totals = _BasisTotals()
    for transaction in transactions:
        _accumulate(totals, transaction)
    net_basis_delta_local = (
        totals.target_basis_in_local + totals.cash_basis_local - totals.source_basis_out_local
    )
    return CorporateActionBasisReconciliation(
        status=_status(totals, net_basis_delta_local, basis_tolerance),
        source_leg_count=totals.source_leg_count,
        target_leg_count=totals.target_leg_count,
        cash_consideration_count=totals.cash_consideration_count,
        source_basis_out_local=totals.source_basis_out_local,
        target_basis_in_local=totals.target_basis_in_local,
        cash_basis_local=totals.cash_basis_local,
        missing_cash_basis_count=totals.missing_cash_basis_count,
        net_basis_delta_local=net_basis_delta_local,
        basis_tolerance=basis_tolerance,
    )


def missing_corporate_action_dependencies(
    transaction: BookedTransaction,
    available_transaction_ids: set[str],
) -> tuple[str, ...]:
    """Return unresolved dependency references in source order."""

    if not is_bundle_a_corporate_action(transaction.transaction_type):
        return ()
    return tuple(
        reference
        for reference in transaction.dependency_reference_ids or ()
        if reference not in available_transaction_ids
    )


def _accumulate(totals: _BasisTotals, transaction: BookedTransaction) -> None:
    transaction_type = normalize_corporate_action_transaction_type(transaction.transaction_type)
    if transaction_type in SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES:
        totals.source_leg_count += 1
        totals.source_basis_out_local += abs(
            transaction.net_cost_local
            if transaction.net_cost_local is not None
            else transaction.gross_transaction_amount
        )
    elif transaction_type in TARGET_BASIS_TRANSFER_TRANSACTION_TYPES:
        totals.target_leg_count += 1
        totals.target_basis_in_local += abs(
            transaction.net_cost_local
            if transaction.net_cost_local is not None
            else transaction.gross_transaction_amount
        )
    elif transaction_type == CASH_CONSIDERATION_TRANSACTION_TYPE:
        totals.cash_consideration_count += 1
        if (
            transaction.allocated_cost_basis_local is None
            or transaction.allocated_cost_basis_local < 0
        ):
            totals.missing_cash_basis_count += 1
        else:
            totals.cash_basis_local += transaction.allocated_cost_basis_local


def _status(
    totals: _BasisTotals,
    net_delta: Decimal,
    tolerance: Decimal,
) -> CorporateActionBasisReconciliationStatus:
    if totals.source_leg_count == 0 or totals.target_leg_count == 0:
        return CorporateActionBasisReconciliationStatus.INSUFFICIENT_LEGS
    if totals.missing_cash_basis_count > 0:
        return CorporateActionBasisReconciliationStatus.INSUFFICIENT_CASH_BASIS
    if abs(net_delta) <= tolerance:
        return CorporateActionBasisReconciliationStatus.BALANCED
    return CorporateActionBasisReconciliationStatus.BASIS_MISMATCH
