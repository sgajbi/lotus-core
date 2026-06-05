from dataclasses import dataclass
from typing import Iterable

from .control_code_normalization import normalize_transaction_control_code
from .sell_models import SellCanonicalTransaction
from .sell_reason_codes import SellValidationReasonCode


@dataclass(frozen=True)
class SellValidationIssue:
    code: SellValidationReasonCode
    field: str
    message: str


class SellValidationError(ValueError):
    def __init__(self, issues: Iterable[SellValidationIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{i.code}: {i.field}" for i in self.issues)
        super().__init__(message or "SELL validation failed")


def validate_sell_transaction(
    txn: SellCanonicalTransaction, *, strict_metadata: bool = False
) -> list[SellValidationIssue]:
    issues: list[SellValidationIssue] = []
    _validate_sell_transaction_type(issues, txn)
    _validate_settlement_date_presence(issues, txn)
    _validate_positive_quantity(issues, txn)
    _validate_positive_gross_amount(issues, txn)
    _validate_currency_fields(issues, txn)
    _validate_date_order(issues, txn)
    _validate_strict_metadata(issues, txn, strict_metadata=strict_metadata)
    return issues


def _validate_sell_transaction_type(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if normalize_transaction_control_code(txn.transaction_type) != "SELL":
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.INVALID_TRANSACTION_TYPE,
                field="transaction_type",
                message="transaction_type must be SELL for SELL canonical validation.",
            )
        )


def _validate_settlement_date_presence(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if txn.settlement_date is None:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.MISSING_SETTLEMENT_DATE,
                field="settlement_date",
                message="settlement_date is required for SELL.",
            )
        )


def _validate_positive_quantity(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if txn.quantity <= 0:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.NON_POSITIVE_QUANTITY,
                field="quantity",
                message="quantity must be greater than zero for SELL.",
            )
        )


def _validate_positive_gross_amount(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if txn.gross_transaction_amount <= 0:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
                field="gross_transaction_amount",
                message="gross_transaction_amount must be greater than zero for SELL.",
            )
        )


def _validate_currency_fields(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if not txn.trade_currency:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.MISSING_TRADE_CURRENCY,
                field="trade_currency",
                message="trade_currency is required.",
            )
        )

    if not txn.currency:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.MISSING_BOOK_CURRENCY,
                field="currency",
                message="currency is required.",
            )
        )


def _validate_date_order(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if txn.settlement_date is not None and txn.transaction_date > txn.settlement_date:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.INVALID_DATE_ORDER,
                field="transaction_date",
                message="transaction_date must be on or before settlement_date.",
            )
        )


def _validate_strict_metadata(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
    *,
    strict_metadata: bool,
) -> None:
    if strict_metadata:
        _validate_strict_linkage_metadata(issues, txn)
        _validate_strict_policy_metadata(issues, txn)


def _validate_strict_linkage_metadata(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if not txn.economic_event_id or not txn.linked_transaction_group_id:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
                field="economic_event_id",
                message=(
                    "economic_event_id and linked_transaction_group_id are required "
                    "under strict metadata validation."
                ),
            )
        )


def _validate_strict_policy_metadata(
    issues: list[SellValidationIssue],
    txn: SellCanonicalTransaction,
) -> None:
    if not txn.calculation_policy_id or not txn.calculation_policy_version:
        issues.append(
            SellValidationIssue(
                code=SellValidationReasonCode.MISSING_POLICY_METADATA,
                field="calculation_policy_id",
                message=(
                    "calculation_policy_id and calculation_policy_version are required "
                    "under strict metadata validation."
                ),
            )
        )
