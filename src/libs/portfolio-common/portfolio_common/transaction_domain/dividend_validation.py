from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .cash_entry_mode import (
    AUTO_GENERATE_CASH_ENTRY_MODE,
    is_upstream_provided_cash_entry_mode,
    normalize_cash_entry_mode,
)
from .dividend_models import DividendCanonicalTransaction
from .dividend_reason_codes import DividendValidationReasonCode


@dataclass(frozen=True)
class DividendValidationIssue:
    code: DividendValidationReasonCode
    field: str
    message: str


class DividendValidationError(ValueError):
    def __init__(self, issues: Iterable[DividendValidationIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{i.code}: {i.field}" for i in self.issues)
        super().__init__(message or "DIVIDEND validation failed")


def validate_dividend_transaction(
    txn: DividendCanonicalTransaction, *, strict_metadata: bool = False
) -> list[DividendValidationIssue]:
    issues: list[DividendValidationIssue] = []

    if txn.transaction_type.upper() != "DIVIDEND":
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.INVALID_TRANSACTION_TYPE,
                field="transaction_type",
                message=(
                    "transaction_type must be DIVIDEND for DIVIDEND canonical validation."
                ),
            )
        )

    if txn.settlement_date is None:
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.MISSING_SETTLEMENT_DATE,
                field="settlement_date",
                message="settlement_date is required for DIVIDEND.",
            )
        )

    if txn.quantity != Decimal(0):
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.NON_ZERO_QUANTITY,
                field="quantity",
                message="quantity must be zero for DIVIDEND.",
            )
        )

    if txn.price != Decimal(0):
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.NON_ZERO_PRICE,
                field="price",
                message="price must be zero for DIVIDEND.",
            )
        )

    if txn.gross_transaction_amount <= 0:
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
                field="gross_transaction_amount",
                message=(
                    "gross_transaction_amount must be greater than zero for DIVIDEND."
                ),
            )
        )

    if not txn.trade_currency:
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.MISSING_TRADE_CURRENCY,
                field="trade_currency",
                message="trade_currency is required.",
            )
        )

    if not txn.currency:
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.MISSING_BOOK_CURRENCY,
                field="currency",
                message="currency is required.",
            )
        )

    if txn.settlement_date is not None and txn.transaction_date > txn.settlement_date:
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.INVALID_DATE_ORDER,
                field="transaction_date",
                message="transaction_date must be on or before settlement_date.",
            )
        )

    if strict_metadata:
        if not txn.economic_event_id or not txn.linked_transaction_group_id:
            issues.append(
                DividendValidationIssue(
                    code=DividendValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
                    field="economic_event_id",
                    message=(
                        "economic_event_id and linked_transaction_group_id are required "
                        "under strict metadata validation."
                    ),
                )
            )

        if not txn.calculation_policy_id or not txn.calculation_policy_version:
            issues.append(
                DividendValidationIssue(
                    code=DividendValidationReasonCode.MISSING_POLICY_METADATA,
                    field="calculation_policy_id",
                    message=(
                        "calculation_policy_id and calculation_policy_version are required "
                        "under strict metadata validation."
                    ),
                )
            )

    cash_entry_mode = normalize_cash_entry_mode(txn.cash_entry_mode)
    has_explicit_cash_entry_mode = txn.cash_entry_mode is not None

    if (
        has_explicit_cash_entry_mode
        and cash_entry_mode == AUTO_GENERATE_CASH_ENTRY_MODE
        and not txn.settlement_cash_account_id
    ):
        issues.append(
            DividendValidationIssue(
                code=DividendValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT,
                field="settlement_cash_account_id",
                message=(
                    "settlement_cash_account_id is required when "
                    "cash_entry_mode is AUTO_GENERATE."
                ),
            )
        )

    if has_explicit_cash_entry_mode and is_upstream_provided_cash_entry_mode(cash_entry_mode):
        if not txn.external_cash_transaction_id:
            issues.append(
                DividendValidationIssue(
                    code=DividendValidationReasonCode.MISSING_EXTERNAL_CASH_LINK,
                    field="external_cash_transaction_id",
                    message=(
                        "external_cash_transaction_id is required when "
                        "cash_entry_mode is UPSTREAM_PROVIDED."
                    ),
                )
            )

    return issues
