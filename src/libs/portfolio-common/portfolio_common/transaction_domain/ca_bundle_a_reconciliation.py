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
from portfolio_common.ca_bundle_a_constants import normalize_ca_bundle_a_transaction_type
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


@dataclass
class _CaBundleAReconciliationAccumulator:
    source_leg_count: int = 0
    target_leg_count: int = 0
    cash_consideration_count: int = 0
    source_basis_out_local: Decimal = Decimal(0)
    target_basis_in_local: Decimal = Decimal(0)


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
    accumulator = _CaBundleAReconciliationAccumulator()
    for event in events:
        _accumulate_reconciliation_event(accumulator, event)

    net_basis_delta_local = accumulator.target_basis_in_local - accumulator.source_basis_out_local
    return CaBundleAReconciliationResult(
        status=_resolve_reconciliation_status(
            accumulator=accumulator,
            net_basis_delta_local=net_basis_delta_local,
            basis_tolerance=basis_tolerance,
        ),
        source_leg_count=accumulator.source_leg_count,
        target_leg_count=accumulator.target_leg_count,
        cash_consideration_count=accumulator.cash_consideration_count,
        source_basis_out_local=accumulator.source_basis_out_local,
        target_basis_in_local=accumulator.target_basis_in_local,
        net_basis_delta_local=net_basis_delta_local,
        basis_tolerance=basis_tolerance,
    )


def _accumulate_reconciliation_event(
    accumulator: _CaBundleAReconciliationAccumulator,
    event: TransactionEvent,
) -> None:
    transaction_type = normalize_ca_bundle_a_transaction_type(event.transaction_type)
    if transaction_type in CA_BUNDLE_A_OUT_TYPES:
        _accumulate_source_leg(accumulator, event)
    elif transaction_type in CA_BUNDLE_A_IN_TYPES:
        _accumulate_target_leg(accumulator, event)
    elif transaction_type == CASH_CONSIDERATION_TRANSACTION_TYPE:
        accumulator.cash_consideration_count += 1


def _accumulate_source_leg(
    accumulator: _CaBundleAReconciliationAccumulator,
    event: TransactionEvent,
) -> None:
    accumulator.source_leg_count += 1
    accumulator.source_basis_out_local += _source_basis_out_local(event)


def _accumulate_target_leg(
    accumulator: _CaBundleAReconciliationAccumulator,
    event: TransactionEvent,
) -> None:
    accumulator.target_leg_count += 1
    accumulator.target_basis_in_local += _target_basis_in_local(event)


def _resolve_reconciliation_status(
    *,
    accumulator: _CaBundleAReconciliationAccumulator,
    net_basis_delta_local: Decimal,
    basis_tolerance: Decimal,
) -> str:
    if accumulator.source_leg_count == 0 or accumulator.target_leg_count == 0:
        return "insufficient_legs"
    if abs(net_basis_delta_local) <= basis_tolerance:
        return "balanced"
    return "basis_mismatch"


def find_missing_ca_bundle_a_dependencies(
    event: TransactionEvent, available_transaction_ids: set[str]
) -> list[str]:
    if not is_ca_bundle_a_transaction_type(event.transaction_type):
        return []
    dependency_ids = event.dependency_reference_ids or []
    return [ref for ref in dependency_ids if ref not in available_transaction_ids]
