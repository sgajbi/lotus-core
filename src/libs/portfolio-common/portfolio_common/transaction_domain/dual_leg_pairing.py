from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from portfolio_common.events import TransactionEvent

from .cash_entry_mode import is_upstream_provided_cash_entry_mode


@dataclass(frozen=True)
class DualLegPairingIssue:
    field: str
    message: str


class DualLegPairingError(ValueError):
    def __init__(self, issues: Iterable[DualLegPairingIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{i.field}: {i.message}" for i in self.issues)
        super().__init__(message or "Dual-leg pairing validation failed")


def validate_upstream_cash_leg_pairing(
    product_leg: TransactionEvent, cash_leg: TransactionEvent
) -> list[DualLegPairingIssue]:
    """
    Transaction-agnostic quality checks for pairing an upstream-provided cash leg.

    This contract is intentionally generic so future transaction types can reuse
    the same pairing logic without duplicating rules.
    """
    issues: list[DualLegPairingIssue] = []

    if not is_upstream_provided_cash_entry_mode(product_leg.cash_entry_mode):
        issues.append(
            DualLegPairingIssue(
                field="cash_entry_mode",
                message="product leg cash_entry_mode must be UPSTREAM_PROVIDED.",
            )
        )

    if product_leg.portfolio_id != cash_leg.portfolio_id:
        issues.append(
            DualLegPairingIssue(
                field="portfolio_id",
                message="product and cash legs must belong to the same portfolio_id.",
            )
        )

    if product_leg.external_cash_transaction_id != cash_leg.transaction_id:
        issues.append(
            DualLegPairingIssue(
                field="external_cash_transaction_id",
                message=(
                    "product leg external_cash_transaction_id must match "
                    "cash leg transaction_id."
                ),
            )
        )

    if cash_leg.transaction_type.upper() != "ADJUSTMENT":
        issues.append(
            DualLegPairingIssue(
                field="transaction_type",
                message="cash leg transaction_type must be ADJUSTMENT.",
            )
        )

    if cash_leg.gross_transaction_amount <= Decimal(0):
        issues.append(
            DualLegPairingIssue(
                field="gross_transaction_amount",
                message="cash leg gross_transaction_amount must be greater than zero.",
            )
        )

    if (
        product_leg.economic_event_id
        and cash_leg.economic_event_id
        and product_leg.economic_event_id != cash_leg.economic_event_id
    ):
        issues.append(
            DualLegPairingIssue(
                field="economic_event_id",
                message="product and cash legs must share economic_event_id when present.",
            )
        )

    if (
        product_leg.linked_transaction_group_id
        and cash_leg.linked_transaction_group_id
        and product_leg.linked_transaction_group_id != cash_leg.linked_transaction_group_id
    ):
        issues.append(
            DualLegPairingIssue(
                field="linked_transaction_group_id",
                message=(
                    "product and cash legs must share linked_transaction_group_id " "when present."
                ),
            )
        )

    return issues


def assert_upstream_cash_leg_pairing(
    product_leg: TransactionEvent, cash_leg: TransactionEvent
) -> None:
    issues = validate_upstream_cash_leg_pairing(product_leg, cash_leg)
    if issues:
        raise DualLegPairingError(issues)
