from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .cash_entry_mode import is_external_cash_entry_mode
from .interest_models import InterestCanonicalTransaction
from .interest_reason_codes import InterestValidationReasonCode


@dataclass(frozen=True)
class InterestValidationIssue:
    code: InterestValidationReasonCode
    field: str
    message: str


class InterestValidationError(ValueError):
    def __init__(self, issues: Iterable[InterestValidationIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{i.code}: {i.field}" for i in self.issues)
        super().__init__(message or "INTEREST validation failed")


def validate_interest_transaction(
    txn: InterestCanonicalTransaction, *, strict_metadata: bool = False
) -> list[InterestValidationIssue]:
    issues: list[InterestValidationIssue] = []

    if txn.transaction_type.upper() != "INTEREST":
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.INVALID_TRANSACTION_TYPE,
                field="transaction_type",
                message=(
                    "transaction_type must be INTEREST for INTEREST canonical validation."
                ),
            )
        )

    if txn.settlement_date is None:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.MISSING_SETTLEMENT_DATE,
                field="settlement_date",
                message="settlement_date is required for INTEREST.",
            )
        )

    if txn.quantity != Decimal(0):
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.NON_ZERO_QUANTITY,
                field="quantity",
                message="quantity must be zero for INTEREST.",
            )
        )

    if txn.price != Decimal(0):
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.NON_ZERO_PRICE,
                field="price",
                message="price must be zero for INTEREST.",
            )
        )

    if txn.gross_transaction_amount <= 0:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
                field="gross_transaction_amount",
                message=(
                    "gross_transaction_amount must be greater than zero for INTEREST."
                ),
            )
        )

    if txn.interest_direction is not None:
        direction = txn.interest_direction.upper()
        if direction not in {"INCOME", "EXPENSE"}:
            issues.append(
                InterestValidationIssue(
                    code=InterestValidationReasonCode.INVALID_INTEREST_DIRECTION,
                    field="interest_direction",
                    message="interest_direction must be INCOME or EXPENSE when provided.",
                )
            )

    withholding_tax_amount = txn.withholding_tax_amount or Decimal(0)
    other_interest_deductions_amount = txn.other_interest_deductions_amount or Decimal(0)

    if withholding_tax_amount < 0:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.NEGATIVE_WITHHOLDING_TAX,
                field="withholding_tax_amount",
                message="withholding_tax_amount must be >= 0.",
            )
        )

    if other_interest_deductions_amount < 0:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.NEGATIVE_OTHER_DEDUCTIONS,
                field="other_interest_deductions_amount",
                message="other_interest_deductions_amount must be >= 0.",
            )
        )

    if txn.net_interest_amount is not None:
        expected_net = (
            txn.gross_transaction_amount
            - withholding_tax_amount
            - other_interest_deductions_amount
        )
        if txn.net_interest_amount != expected_net:
            issues.append(
                InterestValidationIssue(
                    code=InterestValidationReasonCode.NET_INTEREST_RECONCILIATION_MISMATCH,
                    field="net_interest_amount",
                    message=(
                        "net_interest_amount must equal gross_transaction_amount - "
                        "withholding_tax_amount - other_interest_deductions_amount."
                    ),
                )
            )

    if not txn.trade_currency:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.MISSING_TRADE_CURRENCY,
                field="trade_currency",
                message="trade_currency is required.",
            )
        )

    if not txn.currency:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.MISSING_BOOK_CURRENCY,
                field="currency",
                message="currency is required.",
            )
        )

    if txn.settlement_date is not None and txn.transaction_date > txn.settlement_date:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.INVALID_DATE_ORDER,
                field="transaction_date",
                message="transaction_date must be on or before settlement_date.",
            )
        )

    if strict_metadata:
        if not txn.economic_event_id or not txn.linked_transaction_group_id:
            issues.append(
                InterestValidationIssue(
                    code=InterestValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
                    field="economic_event_id",
                    message=(
                        "economic_event_id and linked_transaction_group_id are required "
                        "under strict metadata validation."
                    ),
                )
            )

        if not txn.calculation_policy_id or not txn.calculation_policy_version:
            issues.append(
                InterestValidationIssue(
                    code=InterestValidationReasonCode.MISSING_POLICY_METADATA,
                    field="calculation_policy_id",
                    message=(
                        "calculation_policy_id and calculation_policy_version are required "
                        "under strict metadata validation."
                    ),
                )
            )

    if is_external_cash_entry_mode(txn.cash_entry_mode):
        if not txn.external_cash_transaction_id:
            issues.append(
                InterestValidationIssue(
                    code=InterestValidationReasonCode.MISSING_EXTERNAL_CASH_LINK,
                    field="external_cash_transaction_id",
                    message=(
                        "external_cash_transaction_id is required when "
                        "cash_entry_mode is EXTERNAL."
                    ),
                )
            )

    return issues
