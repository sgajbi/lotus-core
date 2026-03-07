from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from portfolio_common.ca_bundle_a_constants import (
    CA_BUNDLE_A_CASH_CONSIDERATION_TYPE as CASH_CONSIDERATION_TRANSACTION_TYPE,
)
from portfolio_common.ca_bundle_a_constants import (
    CA_BUNDLE_A_SOURCE_OUT_TYPES as CA_BUNDLE_A_OUT_TYPES,
)
from portfolio_common.ca_bundle_a_constants import (
    CA_BUNDLE_A_TARGET_IN_TYPES as CA_BUNDLE_A_IN_TYPES,
)
from portfolio_common.events import TransactionEvent

from .ca_bundle_a_validation import is_ca_bundle_a_transaction_type

DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class CaBundleAReconciliationResult:
    status: str
    source_leg_count: int
    target_leg_count: int
    cash_consideration_count: int
    source_basis_out_local: Decimal
    target_basis_in_local: Decimal
    net_basis_delta_local: Decimal
    basis_tolerance: Decimal


def _source_basis_out_local(event: TransactionEvent) -> Decimal:
    if event.net_cost_local is not None:
        return abs(event.net_cost_local)
    return abs(event.gross_transaction_amount)


def _target_basis_in_local(event: TransactionEvent) -> Decimal:
    if event.net_cost_local is not None:
        return abs(event.net_cost_local)
    return abs(event.gross_transaction_amount)


def evaluate_ca_bundle_a_reconciliation(
    events: Iterable[TransactionEvent],
    *,
    basis_tolerance: Decimal = DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE,
) -> CaBundleAReconciliationResult:
    source_leg_count = 0
    target_leg_count = 0
    cash_consideration_count = 0
    source_basis_out_local = Decimal(0)
    target_basis_in_local = Decimal(0)

    for event in events:
        transaction_type = event.transaction_type.upper()
        if transaction_type in CA_BUNDLE_A_OUT_TYPES:
            source_leg_count += 1
            source_basis_out_local += _source_basis_out_local(event)
        elif transaction_type in CA_BUNDLE_A_IN_TYPES:
            target_leg_count += 1
            target_basis_in_local += _target_basis_in_local(event)
        elif transaction_type == CASH_CONSIDERATION_TRANSACTION_TYPE:
            cash_consideration_count += 1

    net_basis_delta_local = target_basis_in_local - source_basis_out_local

    if source_leg_count == 0 or target_leg_count == 0:
        status = "insufficient_legs"
    elif abs(net_basis_delta_local) <= basis_tolerance:
        status = "balanced"
    else:
        status = "basis_mismatch"

    return CaBundleAReconciliationResult(
        status=status,
        source_leg_count=source_leg_count,
        target_leg_count=target_leg_count,
        cash_consideration_count=cash_consideration_count,
        source_basis_out_local=source_basis_out_local,
        target_basis_in_local=target_basis_in_local,
        net_basis_delta_local=net_basis_delta_local,
        basis_tolerance=basis_tolerance,
    )


def find_missing_ca_bundle_a_dependencies(
    event: TransactionEvent, available_transaction_ids: set[str]
) -> list[str]:
    if not is_ca_bundle_a_transaction_type(event.transaction_type):
        return []
    dependency_ids = event.dependency_reference_ids or []
    return [ref for ref in dependency_ids if ref not in available_transaction_ids]
