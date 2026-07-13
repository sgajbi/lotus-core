"""Apply deterministic linkage and calculation-policy metadata at booking time."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from .booked import BookedTransaction
from .settlement import resolve_cash_entry_mode

BUY_DEFAULT_POLICY_ID = "BUY_DEFAULT_POLICY"
BUY_DEFAULT_POLICY_VERSION = "1.0.0"
SELL_FIFO_POLICY_ID = "SELL_FIFO_POLICY"
SELL_AVCO_POLICY_ID = "SELL_AVCO_POLICY"
SELL_DEFAULT_POLICY_VERSION = "1.0.0"
DIVIDEND_DEFAULT_POLICY_ID = "DIVIDEND_DEFAULT_POLICY"
DIVIDEND_DEFAULT_POLICY_VERSION = "1.0.0"
INTEREST_DEFAULT_POLICY_ID = "INTEREST_DEFAULT_POLICY"
INTEREST_DEFAULT_POLICY_VERSION = "1.0.0"

PolicyIdResolver = Callable[[str | CostBasisMethod | None], str]


@dataclass(frozen=True, slots=True)
class BookingMetadataPolicy:
    """Define deterministic metadata defaults for one booked transaction family."""

    linkage_prefix: str
    default_policy_version: str
    policy_id_resolver: PolicyIdResolver
    resolves_cash_entry_mode: bool = False


def enrich_booking_metadata(
    transaction: BookedTransaction,
    *,
    cost_basis_method: str | CostBasisMethod | None = None,
) -> BookedTransaction:
    """Return the transaction with deterministic missing booking metadata populated."""

    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    policy = _BOOKING_METADATA_POLICIES.get(transaction_type)
    if policy is None:
        return transaction

    economic_event_id = transaction.economic_event_id or (
        f"EVT-{policy.linkage_prefix}-{transaction.portfolio_id}-{transaction.transaction_id}"
    )
    linked_group_id = transaction.linked_transaction_group_id or (
        f"LTG-{policy.linkage_prefix}-{transaction.portfolio_id}-{transaction.transaction_id}"
    )
    calculation_policy_id = transaction.calculation_policy_id or policy.policy_id_resolver(
        cost_basis_method
    )
    calculation_policy_version = (
        transaction.calculation_policy_version or policy.default_policy_version
    )
    cash_entry_mode = transaction.cash_entry_mode
    if policy.resolves_cash_entry_mode:
        cash_entry_mode = resolve_cash_entry_mode(cash_entry_mode).value

    return replace(
        transaction,
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        calculation_policy_id=calculation_policy_id,
        calculation_policy_version=calculation_policy_version,
        cash_entry_mode=cash_entry_mode,
    )


def _constant_policy_id(policy_id: str) -> PolicyIdResolver:
    def resolve(_cost_basis_method: str | CostBasisMethod | None) -> str:
        return policy_id

    return resolve


def _sell_policy_id(cost_basis_method: str | CostBasisMethod | None) -> str:
    if normalize_cost_basis_method(cost_basis_method) is CostBasisMethod.AVCO:
        return SELL_AVCO_POLICY_ID
    return SELL_FIFO_POLICY_ID


_BOOKING_METADATA_POLICIES = {
    "BUY": BookingMetadataPolicy(
        linkage_prefix="BUY",
        default_policy_version=BUY_DEFAULT_POLICY_VERSION,
        policy_id_resolver=_constant_policy_id(BUY_DEFAULT_POLICY_ID),
    ),
    "SELL": BookingMetadataPolicy(
        linkage_prefix="SELL",
        default_policy_version=SELL_DEFAULT_POLICY_VERSION,
        policy_id_resolver=_sell_policy_id,
    ),
    "DIVIDEND": BookingMetadataPolicy(
        linkage_prefix="DIVIDEND",
        default_policy_version=DIVIDEND_DEFAULT_POLICY_VERSION,
        policy_id_resolver=_constant_policy_id(DIVIDEND_DEFAULT_POLICY_ID),
        resolves_cash_entry_mode=True,
    ),
    "INTEREST": BookingMetadataPolicy(
        linkage_prefix="INTEREST",
        default_policy_version=INTEREST_DEFAULT_POLICY_VERSION,
        policy_id_resolver=_constant_policy_id(INTEREST_DEFAULT_POLICY_ID),
        resolves_cash_entry_mode=True,
    ),
}
