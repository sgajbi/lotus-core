from dataclasses import dataclass
from typing import Iterable

from .buy_models import BuyCanonicalTransaction
from .buy_reason_codes import BuyValidationReasonCode
from .control_code_normalization import normalize_transaction_control_code


@dataclass(frozen=True)
class BuyValidationIssue:
    code: BuyValidationReasonCode
    field: str
    message: str


class BuyValidationError(ValueError):
    def __init__(self, issues: Iterable[BuyValidationIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{i.code}: {i.field}" for i in self.issues)
        super().__init__(message or "BUY validation failed")


def validate_buy_transaction(
    txn: BuyCanonicalTransaction, *, strict_metadata: bool = False
) -> list[BuyValidationIssue]:
    issues: list[BuyValidationIssue] = []
    _validate_buy_transaction_type(issues, txn)
    _validate_settlement_date_presence(issues, txn)
    _validate_positive_quantity(issues, txn)
    _validate_positive_gross_amount(issues, txn)
    _validate_currency_fields(issues, txn)
    _validate_date_order(issues, txn)
    _validate_strict_metadata(issues, txn, strict_metadata=strict_metadata)
    return issues


def _validate_buy_transaction_type(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if normalize_transaction_control_code(txn.transaction_type) != "BUY":
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.INVALID_TRANSACTION_TYPE,
                field="transaction_type",
                message="transaction_type must be BUY for BUY canonical validation.",
            )
        )


def _validate_settlement_date_presence(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if txn.settlement_date is None:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.MISSING_SETTLEMENT_DATE,
                field="settlement_date",
                message="settlement_date is required for BUY.",
            )
        )


def _validate_positive_quantity(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if txn.quantity <= 0:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.NON_POSITIVE_QUANTITY,
                field="quantity",
                message="quantity must be greater than zero for BUY.",
            )
        )


def _validate_positive_gross_amount(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if txn.gross_transaction_amount <= 0:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
                field="gross_transaction_amount",
                message="gross_transaction_amount must be greater than zero for BUY.",
            )
        )


def _validate_currency_fields(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if not txn.trade_currency:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.MISSING_TRADE_CURRENCY,
                field="trade_currency",
                message="trade_currency is required.",
            )
        )

    if not txn.currency:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.MISSING_BOOK_CURRENCY,
                field="currency",
                message="currency is required.",
            )
        )


def _validate_date_order(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if txn.settlement_date is not None and txn.transaction_date > txn.settlement_date:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.INVALID_DATE_ORDER,
                field="transaction_date",
                message="transaction_date must be on or before settlement_date.",
            )
        )


def _validate_strict_metadata(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
    *,
    strict_metadata: bool,
) -> None:
    if strict_metadata:
        _validate_strict_linkage_metadata(issues, txn)
        _validate_strict_policy_metadata(issues, txn)


def _validate_strict_linkage_metadata(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if not txn.economic_event_id or not txn.linked_transaction_group_id:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
                field="economic_event_id",
                message=(
                    "economic_event_id and linked_transaction_group_id are required "
                    "under strict metadata validation."
                ),
            )
        )


def _validate_strict_policy_metadata(
    issues: list[BuyValidationIssue],
    txn: BuyCanonicalTransaction,
) -> None:
    if not txn.calculation_policy_id or not txn.calculation_policy_version:
        issues.append(
            BuyValidationIssue(
                code=BuyValidationReasonCode.MISSING_POLICY_METADATA,
                field="calculation_policy_id",
                message=(
                    "calculation_policy_id and calculation_policy_version are required "
                    "under strict metadata validation."
                ),
            )
        )
