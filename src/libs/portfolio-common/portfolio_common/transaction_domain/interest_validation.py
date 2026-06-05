from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .cash_entry_mode import (
    AUTO_GENERATE_CASH_ENTRY_MODE,
    is_upstream_provided_cash_entry_mode,
    normalize_cash_entry_mode,
)
from .control_code_normalization import normalize_transaction_control_code
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
    _validate_interest_transaction_type(issues, txn)
    _validate_settlement_date_presence(issues, txn)
    _validate_zero_quantity_and_price(issues, txn)
    _validate_gross_amount(issues, txn)
    _validate_interest_direction(issues, txn)
    _validate_deductions_and_net_amount(issues, txn)
    _validate_currency_fields(issues, txn)
    _validate_date_order(issues, txn)
    _validate_strict_metadata(issues, txn, strict_metadata=strict_metadata)
    _validate_cash_entry_policy(issues, txn)
    return issues


def _validate_interest_transaction_type(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
    if normalize_transaction_control_code(txn.transaction_type) != "INTEREST":
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.INVALID_TRANSACTION_TYPE,
                field="transaction_type",
                message=("transaction_type must be INTEREST for INTEREST canonical validation."),
            )
        )


def _validate_settlement_date_presence(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
    if txn.settlement_date is None:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.MISSING_SETTLEMENT_DATE,
                field="settlement_date",
                message="settlement_date is required for INTEREST.",
            )
        )


def _validate_zero_quantity_and_price(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
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


def _validate_gross_amount(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
    if txn.gross_transaction_amount <= 0:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
                field="gross_transaction_amount",
                message=("gross_transaction_amount must be greater than zero for INTEREST."),
            )
        )


def _validate_interest_direction(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
    if txn.interest_direction is not None:
        direction = normalize_transaction_control_code(txn.interest_direction)
        if direction not in {"INCOME", "EXPENSE"}:
            issues.append(
                InterestValidationIssue(
                    code=InterestValidationReasonCode.INVALID_INTEREST_DIRECTION,
                    field="interest_direction",
                    message="interest_direction must be INCOME or EXPENSE when provided.",
                )
            )


def _validate_deductions_and_net_amount(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
    withholding_tax_amount = txn.withholding_tax_amount or Decimal(0)
    other_interest_deductions_amount = txn.other_interest_deductions_amount or Decimal(0)
    _validate_nonnegative_deduction(
        issues,
        value=withholding_tax_amount,
        field="withholding_tax_amount",
        code=InterestValidationReasonCode.NEGATIVE_WITHHOLDING_TAX,
        message="withholding_tax_amount must be >= 0.",
    )
    _validate_nonnegative_deduction(
        issues,
        value=other_interest_deductions_amount,
        field="other_interest_deductions_amount",
        code=InterestValidationReasonCode.NEGATIVE_OTHER_DEDUCTIONS,
        message="other_interest_deductions_amount must be >= 0.",
    )
    _validate_net_interest_amount(
        issues,
        txn=txn,
        withholding_tax_amount=withholding_tax_amount,
        other_interest_deductions_amount=other_interest_deductions_amount,
    )


def _validate_nonnegative_deduction(
    issues: list[InterestValidationIssue],
    *,
    value: Decimal,
    field: str,
    code: InterestValidationReasonCode,
    message: str,
) -> None:
    if value < 0:
        issues.append(InterestValidationIssue(code=code, field=field, message=message))


def _validate_net_interest_amount(
    issues: list[InterestValidationIssue],
    *,
    txn: InterestCanonicalTransaction,
    withholding_tax_amount: Decimal,
    other_interest_deductions_amount: Decimal,
) -> None:
    if txn.net_interest_amount is not None:
        expected_net = (
            txn.gross_transaction_amount - withholding_tax_amount - other_interest_deductions_amount
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


def _validate_currency_fields(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
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


def _validate_date_order(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
    if txn.settlement_date is not None and txn.transaction_date > txn.settlement_date:
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.INVALID_DATE_ORDER,
                field="transaction_date",
                message="transaction_date must be on or before settlement_date.",
            )
        )


def _validate_strict_metadata(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
    *,
    strict_metadata: bool,
) -> None:
    if strict_metadata:
        _validate_strict_linkage_metadata(issues, txn)
        _validate_strict_policy_metadata(issues, txn)


def _validate_strict_linkage_metadata(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
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


def _validate_strict_policy_metadata(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
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


def _validate_cash_entry_policy(
    issues: list[InterestValidationIssue],
    txn: InterestCanonicalTransaction,
) -> None:
    cash_entry_mode = normalize_cash_entry_mode(txn.cash_entry_mode)
    has_explicit_cash_entry_mode = txn.cash_entry_mode is not None
    if _requires_settlement_cash_account(txn, cash_entry_mode, has_explicit_cash_entry_mode):
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT,
                field="settlement_cash_account_id",
                message=(
                    "settlement_cash_account_id is required when cash_entry_mode is AUTO_GENERATE."
                ),
            )
        )
    if _requires_external_cash_link(txn, cash_entry_mode, has_explicit_cash_entry_mode):
        issues.append(
            InterestValidationIssue(
                code=InterestValidationReasonCode.MISSING_EXTERNAL_CASH_LINK,
                field="external_cash_transaction_id",
                message=(
                    "external_cash_transaction_id is required when "
                    "cash_entry_mode is UPSTREAM_PROVIDED."
                ),
            )
        )


def _requires_settlement_cash_account(
    txn: InterestCanonicalTransaction,
    cash_entry_mode: str,
    has_explicit_cash_entry_mode: bool,
) -> bool:
    return (
        has_explicit_cash_entry_mode
        and cash_entry_mode == AUTO_GENERATE_CASH_ENTRY_MODE
        and not txn.settlement_cash_account_id
    )


def _requires_external_cash_link(
    txn: InterestCanonicalTransaction,
    cash_entry_mode: str,
    has_explicit_cash_entry_mode: bool,
) -> bool:
    return (
        has_explicit_cash_entry_mode
        and is_upstream_provided_cash_entry_mode(cash_entry_mode)
        and not txn.external_cash_transaction_id
    )
