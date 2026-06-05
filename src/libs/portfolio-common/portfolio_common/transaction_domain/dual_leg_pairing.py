from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from portfolio_common.events import TransactionEvent

from .cash_entry_mode import is_upstream_provided_cash_entry_mode
from .control_code_normalization import normalize_transaction_control_code


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
    _validate_product_leg_cash_entry_mode(issues, product_leg)
    _validate_matching_portfolio(issues, product_leg, cash_leg)
    _validate_external_cash_transaction_id(issues, product_leg, cash_leg)
    _validate_cash_leg_transaction_type(issues, cash_leg)
    _validate_cash_leg_gross_amount(issues, cash_leg)
    _validate_economic_event_id(issues, product_leg, cash_leg)
    _validate_linked_transaction_group_id(issues, product_leg, cash_leg)
    return issues


def _validate_product_leg_cash_entry_mode(
    issues: list[DualLegPairingIssue],
    product_leg: TransactionEvent,
) -> None:
    if not is_upstream_provided_cash_entry_mode(product_leg.cash_entry_mode):
        issues.append(
            DualLegPairingIssue(
                field="cash_entry_mode",
                message="product leg cash_entry_mode must be UPSTREAM_PROVIDED.",
            )
        )


def _validate_matching_portfolio(
    issues: list[DualLegPairingIssue],
    product_leg: TransactionEvent,
    cash_leg: TransactionEvent,
) -> None:
    if product_leg.portfolio_id != cash_leg.portfolio_id:
        issues.append(
            DualLegPairingIssue(
                field="portfolio_id",
                message="product and cash legs must belong to the same portfolio_id.",
            )
        )


def _validate_external_cash_transaction_id(
    issues: list[DualLegPairingIssue],
    product_leg: TransactionEvent,
    cash_leg: TransactionEvent,
) -> None:
    if product_leg.external_cash_transaction_id != cash_leg.transaction_id:
        issues.append(
            DualLegPairingIssue(
                field="external_cash_transaction_id",
                message=(
                    "product leg external_cash_transaction_id must match cash leg transaction_id."
                ),
            )
        )


def _validate_cash_leg_transaction_type(
    issues: list[DualLegPairingIssue],
    cash_leg: TransactionEvent,
) -> None:
    if normalize_transaction_control_code(cash_leg.transaction_type) != "ADJUSTMENT":
        issues.append(
            DualLegPairingIssue(
                field="transaction_type",
                message="cash leg transaction_type must be ADJUSTMENT.",
            )
        )


def _validate_cash_leg_gross_amount(
    issues: list[DualLegPairingIssue],
    cash_leg: TransactionEvent,
) -> None:
    if cash_leg.gross_transaction_amount <= Decimal(0):
        issues.append(
            DualLegPairingIssue(
                field="gross_transaction_amount",
                message="cash leg gross_transaction_amount must be greater than zero.",
            )
        )


def _validate_economic_event_id(
    issues: list[DualLegPairingIssue],
    product_leg: TransactionEvent,
    cash_leg: TransactionEvent,
) -> None:
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


def _validate_linked_transaction_group_id(
    issues: list[DualLegPairingIssue],
    product_leg: TransactionEvent,
    cash_leg: TransactionEvent,
) -> None:
    if (
        product_leg.linked_transaction_group_id
        and cash_leg.linked_transaction_group_id
        and product_leg.linked_transaction_group_id != cash_leg.linked_transaction_group_id
    ):
        issues.append(
            DualLegPairingIssue(
                field="linked_transaction_group_id",
                message=(
                    "product and cash legs must share linked_transaction_group_id when present."
                ),
            )
        )


def assert_upstream_cash_leg_pairing(
    product_leg: TransactionEvent, cash_leg: TransactionEvent
) -> None:
    issues = validate_upstream_cash_leg_pairing(product_leg, cash_leg)
    if issues:
        raise DualLegPairingError(issues)
