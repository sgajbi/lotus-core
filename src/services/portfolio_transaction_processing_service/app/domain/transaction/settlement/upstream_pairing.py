"""Validate product and cash legs supplied as one upstream settlement pair."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .cash_entry import is_upstream_provided_cash_entry_mode
from .cash_movement import (
    ORDINARY_SETTLEMENT_TRANSACTION_TYPES,
    calculate_settlement_cash_movement,
)


@dataclass(frozen=True, slots=True)
class UpstreamCashLegPairingIssue:
    """Describe one invariant violation in an upstream product/cash pair."""

    field: str
    message: str


class UpstreamCashLegPairingError(ValueError):
    """Raise all pairing violations together for source-safe diagnosis."""

    def __init__(self, issues: Iterable[UpstreamCashLegPairingIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{issue.field}: {issue.message}" for issue in self.issues)
        super().__init__(message or "Dual-leg pairing validation failed")


def validate_upstream_cash_leg_pairing(
    product_leg: BookedTransaction,
    cash_leg: BookedTransaction,
) -> list[UpstreamCashLegPairingIssue]:
    """Return every invariant violation for one upstream product/cash pair."""

    issues: list[UpstreamCashLegPairingIssue] = []
    if not is_upstream_provided_cash_entry_mode(product_leg.cash_entry_mode):
        issues.append(
            UpstreamCashLegPairingIssue(
                field="cash_entry_mode",
                message="product leg cash_entry_mode must be UPSTREAM_PROVIDED.",
            )
        )
    if product_leg.portfolio_id != cash_leg.portfolio_id:
        issues.append(
            UpstreamCashLegPairingIssue(
                field="portfolio_id",
                message="product and cash legs must belong to the same portfolio_id.",
            )
        )
    if product_leg.external_cash_transaction_id != cash_leg.transaction_id:
        issues.append(
            UpstreamCashLegPairingIssue(
                field="external_cash_transaction_id",
                message=(
                    "product leg external_cash_transaction_id must match cash leg transaction_id."
                ),
            )
        )
    if normalize_transaction_control_code(cash_leg.transaction_type) != "ADJUSTMENT":
        issues.append(
            UpstreamCashLegPairingIssue(
                field="transaction_type",
                message="cash leg transaction_type must be ADJUSTMENT.",
            )
        )
    if cash_leg.gross_transaction_amount <= Decimal(0):
        issues.append(
            UpstreamCashLegPairingIssue(
                field="gross_transaction_amount",
                message="cash leg gross_transaction_amount must be greater than zero.",
            )
        )
    product_type = normalize_transaction_control_code(product_leg.transaction_type)
    if product_type in ORDINARY_SETTLEMENT_TRANSACTION_TYPES:
        expected_amount = calculate_settlement_cash_movement(product_leg).amount
        if cash_leg.gross_transaction_amount != expected_amount:
            issues.append(
                UpstreamCashLegPairingIssue(
                    field="gross_transaction_amount",
                    message=(
                        "cash leg gross_transaction_amount must equal the canonical net "
                        f"settlement amount {expected_amount}."
                    ),
                )
            )
    _validate_shared_identifier(
        issues,
        field="economic_event_id",
        product_value=product_leg.economic_event_id,
        cash_value=cash_leg.economic_event_id,
    )
    _validate_shared_identifier(
        issues,
        field="linked_transaction_group_id",
        product_value=product_leg.linked_transaction_group_id,
        cash_value=cash_leg.linked_transaction_group_id,
    )
    return issues


def assert_upstream_cash_leg_pairing(
    product_leg: BookedTransaction,
    cash_leg: BookedTransaction,
) -> None:
    """Raise when an upstream product/cash pair violates settlement invariants."""

    issues = validate_upstream_cash_leg_pairing(product_leg, cash_leg)
    if issues:
        raise UpstreamCashLegPairingError(issues)


def _validate_shared_identifier(
    issues: list[UpstreamCashLegPairingIssue],
    *,
    field: str,
    product_value: str | None,
    cash_value: str | None,
) -> None:
    normalized_product_value = (product_value or "").strip()
    normalized_cash_value = (cash_value or "").strip()
    if normalized_product_value and normalized_product_value == normalized_cash_value:
        return
    issues.append(
        UpstreamCashLegPairingIssue(
            field=field,
            message=f"product and cash legs must carry the same non-empty {field}.",
        )
    )
