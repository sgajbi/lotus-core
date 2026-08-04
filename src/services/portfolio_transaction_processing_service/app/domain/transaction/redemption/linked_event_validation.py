"""Reject ambiguous interest economics within linked redemption event groups."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .accrued_interest import is_generated_redemption_accrued_interest
from .economics import REDEMPTION_TRANSACTION_TYPES


class RedemptionLinkedEventValidationReasonCode(StrEnum):
    """Stable failure reasons for linked redemption event ambiguity."""

    DUPLICATE_ACCRUED_INTEREST = "REDEMPTION_017_DUPLICATE_LINKED_INTEREST"


@dataclass(frozen=True, slots=True)
class RedemptionLinkedEventValidationError(ValueError):
    """Report a linked group that can count the same interest economics twice."""

    reason_code: RedemptionLinkedEventValidationReasonCode
    linked_transaction_group_id: str
    redemption_transaction_ids: tuple[str, ...]
    interest_transaction_ids: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"{self.reason_code.value}: linked_transaction_group_id: linked group "
            f"{self.linked_transaction_group_id} contains redemption accrued-interest proceeds "
            "and separate INTEREST transactions without a governed netting policy"
        )


def requires_linked_redemption_interest_history(transaction: BookedTransaction) -> bool:
    """Return whether the incoming leg can complete an ambiguous linked-income group."""

    if not _normalized_group_id(transaction):
        return False
    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    return transaction_type == "INTEREST" or (
        transaction_type in REDEMPTION_TRANSACTION_TYPES
        and _has_accrued_interest_proceeds(transaction)
    )


def assert_linked_redemption_interest_unambiguous(
    *,
    incoming: BookedTransaction,
    history: Sequence[BookedTransaction],
) -> None:
    """Fail before calculation when one linked group carries interest twice."""

    group_id = _normalized_group_id(incoming)
    if not group_id:
        return
    group = tuple(
        transaction
        for transaction in (*history, incoming)
        if _normalized_group_id(transaction) == group_id
    )
    redemptions_by_id = {
        transaction.transaction_id.strip(): transaction
        for transaction in group
        if normalize_transaction_control_code(transaction.transaction_type)
        in REDEMPTION_TRANSACTION_TYPES
    }
    redemption_ids = tuple(
        sorted(
            transaction_id
            for transaction_id, transaction in redemptions_by_id.items()
            if _has_accrued_interest_proceeds(transaction)
        )
    )
    interest_ids = tuple(
        sorted(
            transaction.transaction_id.strip()
            for transaction in group
            if normalize_transaction_control_code(transaction.transaction_type) == "INTEREST"
            and not _is_generated_component_for_group(transaction, redemptions_by_id)
        )
    )
    if redemption_ids and interest_ids:
        raise RedemptionLinkedEventValidationError(
            reason_code=(RedemptionLinkedEventValidationReasonCode.DUPLICATE_ACCRUED_INTEREST),
            linked_transaction_group_id=group_id,
            redemption_transaction_ids=redemption_ids,
            interest_transaction_ids=interest_ids,
        )


def _is_generated_component_for_group(
    interest: BookedTransaction,
    redemptions_by_id: dict[str, BookedTransaction],
) -> bool:
    if not is_generated_redemption_accrued_interest(interest):
        return False
    source_id = (interest.originating_transaction_id or "").strip()
    redemption = redemptions_by_id.get(source_id)
    if redemption is None:
        return False
    return normalize_transaction_control_code(
        interest.originating_transaction_type
    ) == normalize_transaction_control_code(redemption.transaction_type) and _normalized_group_id(
        interest
    ) == _normalized_group_id(redemption)


def _has_accrued_interest_proceeds(transaction: BookedTransaction) -> bool:
    value = transaction.accrued_interest_proceeds_local
    return isinstance(value, Decimal) and value.is_finite() and value > 0


def _normalized_group_id(transaction: BookedTransaction) -> str:
    return (transaction.linked_transaction_group_id or "").strip()
