"""Canonical ownership identity for deterministic generated transactions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from portfolio_common.domain.transaction.type_registry import (
    production_transaction_types_for_lifecycle_families,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

_REDEMPTION_TRANSACTION_TYPES = production_transaction_types_for_lifecycle_families("redemption")
_REDEMPTION_ACCRUED_INTEREST_COMPONENT = "REDEMPTION_ACCRUED_INTEREST"
_REDEMPTION_ACCRUED_INTEREST_LINK = "REDEMPTION_TO_ACCRUED_INTEREST"


class TransactionIdentityCandidate(Protocol):
    """Expose only metadata needed to classify transaction-id ownership."""

    transaction_id: str
    portfolio_id: str
    transaction_type: str
    originating_transaction_id: str | None
    originating_transaction_type: str | None
    cash_entry_mode: str | None
    component_type: str | None
    component_id: str | None
    link_type: str | None


class TransactionIdentityFamily(StrEnum):
    """Distinguish source-owned ids from the two deterministic child families."""

    SOURCE = "source"
    GENERATED_SETTLEMENT_CASH = "generated_settlement_cash"
    REDEMPTION_ACCRUED_INTEREST = "redemption_accrued_interest"


@dataclass(frozen=True, slots=True)
class TransactionIdentityOwnership:
    """Bind one global transaction id to its canonical ownership scope."""

    family: TransactionIdentityFamily
    transaction_id: str
    portfolio_id: str
    originating_transaction_id: str | None = None
    originating_transaction_type: str | None = None


def canonical_transaction_identity_record_values(
    values: Mapping[str, object],
    ownership: TransactionIdentityOwnership,
) -> dict[str, object]:
    """Project canonical ownership keys onto a transaction persistence payload."""

    canonical_values = dict(values)
    canonical_values["transaction_id"] = ownership.transaction_id
    canonical_values["portfolio_id"] = ownership.portfolio_id
    if ownership.family is not TransactionIdentityFamily.SOURCE:
        canonical_values["originating_transaction_id"] = ownership.originating_transaction_id
        canonical_values["originating_transaction_type"] = ownership.originating_transaction_type
    return canonical_values


def transaction_identity_ownership(
    candidate: TransactionIdentityCandidate,
) -> TransactionIdentityOwnership:
    """Classify complete canonical child metadata; suffixes alone remain source-owned."""

    transaction_id = _required_identifier(candidate.transaction_id, "transaction_id")
    portfolio_id = _required_identifier(candidate.portfolio_id, "portfolio_id")
    originating_transaction_id = _optional_identifier(
        getattr(candidate, "originating_transaction_id", None)
    )
    originating_transaction_type: str | None = normalize_transaction_control_code(
        getattr(candidate, "originating_transaction_type", None)
    )
    if _is_generated_settlement_cash(candidate, originating_transaction_id):
        family = TransactionIdentityFamily.GENERATED_SETTLEMENT_CASH
    elif _is_redemption_accrued_interest(candidate, originating_transaction_id):
        family = TransactionIdentityFamily.REDEMPTION_ACCRUED_INTEREST
    else:
        family = TransactionIdentityFamily.SOURCE
        originating_transaction_id = None
        originating_transaction_type = None
    return TransactionIdentityOwnership(
        family=family,
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        originating_transaction_id=originating_transaction_id,
        originating_transaction_type=originating_transaction_type,
    )


def require_generated_transaction_identity(
    candidate: TransactionIdentityCandidate,
) -> TransactionIdentityOwnership:
    """Return generated ownership or reject incomplete/suffix-only masquerades."""

    ownership = transaction_identity_ownership(candidate)
    if ownership.family is TransactionIdentityFamily.SOURCE:
        raise ValueError("transaction is not a canonical generated child")
    return ownership


def _is_generated_settlement_cash(
    candidate: TransactionIdentityCandidate,
    originating_transaction_id: str | None,
) -> bool:
    originating_type = normalize_transaction_control_code(
        getattr(candidate, "originating_transaction_type", None)
    )
    return (
        bool(originating_transaction_id)
        and candidate.transaction_id.strip() == f"{originating_transaction_id}-CASHLEG"
        and normalize_transaction_control_code(candidate.transaction_type) == "ADJUSTMENT"
        and normalize_transaction_control_code(getattr(candidate, "cash_entry_mode", None))
        == "AUTO_GENERATE"
        and bool(originating_type)
        and normalize_transaction_control_code(getattr(candidate, "link_type", None))
        == f"{originating_type}_TO_CASH"
        and not normalize_transaction_control_code(getattr(candidate, "component_type", None))
        and not _optional_identifier(getattr(candidate, "component_id", None))
    )


def _is_redemption_accrued_interest(
    candidate: TransactionIdentityCandidate,
    originating_transaction_id: str | None,
) -> bool:
    if not originating_transaction_id:
        return False
    expected_transaction_id = f"{originating_transaction_id}-ACCRUED-INTEREST"
    return (
        candidate.transaction_id.strip() == expected_transaction_id
        and normalize_transaction_control_code(candidate.transaction_type) == "INTEREST"
        and normalize_transaction_control_code(getattr(candidate, "component_type", None))
        == _REDEMPTION_ACCRUED_INTEREST_COMPONENT
        and getattr(candidate, "component_id", None) == f"{expected_transaction_id}:v1"
        and normalize_transaction_control_code(
            getattr(candidate, "originating_transaction_type", None)
        )
        in _REDEMPTION_TRANSACTION_TYPES
        and normalize_transaction_control_code(getattr(candidate, "link_type", None))
        == _REDEMPTION_ACCRUED_INTEREST_LINK
    )


def _required_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonblank string")
    return value.strip()


def _optional_identifier(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
