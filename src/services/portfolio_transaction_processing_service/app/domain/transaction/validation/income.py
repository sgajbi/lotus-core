"""Validate canonical DIVIDEND and INTEREST booked transactions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from ..settlement import (
    CashEntryMode,
    is_upstream_provided_cash_entry_mode,
    resolve_cash_entry_mode,
)
from .issues import TransactionValidationIssue
from .reason_codes import DividendValidationReasonCode, InterestValidationReasonCode

IncomeValidationReasonCode = DividendValidationReasonCode | InterestValidationReasonCode


@dataclass(frozen=True, slots=True)
class IncomeValidationPolicy:
    """Bind one income family to its stable validation reason codes."""

    transaction_type: str
    invalid_type_code: IncomeValidationReasonCode
    missing_settlement_code: IncomeValidationReasonCode
    non_zero_quantity_code: IncomeValidationReasonCode
    non_zero_price_code: IncomeValidationReasonCode
    non_positive_gross_code: IncomeValidationReasonCode
    missing_trade_currency_code: IncomeValidationReasonCode
    missing_book_currency_code: IncomeValidationReasonCode
    invalid_date_order_code: IncomeValidationReasonCode
    missing_linkage_code: IncomeValidationReasonCode
    missing_policy_code: IncomeValidationReasonCode
    missing_external_cash_link_code: IncomeValidationReasonCode
    missing_settlement_cash_account_code: IncomeValidationReasonCode


def validate_dividend_transaction(
    transaction: BookedTransaction,
    *,
    strict_metadata: bool = False,
) -> list[TransactionValidationIssue]:
    """Return canonical DIVIDEND validation findings without mutating the transaction."""

    issues = _validate_income_basics(transaction, _DIVIDEND_VALIDATION_POLICY)
    _validate_income_metadata(
        issues,
        transaction,
        _DIVIDEND_VALIDATION_POLICY,
        strict_metadata=strict_metadata,
    )
    _validate_income_cash_entry(issues, transaction, _DIVIDEND_VALIDATION_POLICY)
    return issues


def validate_interest_transaction(
    transaction: BookedTransaction,
    *,
    strict_metadata: bool = False,
) -> list[TransactionValidationIssue]:
    """Return canonical INTEREST validation findings without mutating the transaction."""

    issues = _validate_income_basics(transaction, _INTEREST_VALIDATION_POLICY)
    _validate_interest_direction(issues, transaction)
    _validate_interest_amounts(issues, transaction)
    _validate_income_metadata(
        issues,
        transaction,
        _INTEREST_VALIDATION_POLICY,
        strict_metadata=strict_metadata,
    )
    _validate_income_cash_entry(issues, transaction, _INTEREST_VALIDATION_POLICY)
    return issues


def _validate_income_basics(
    transaction: BookedTransaction,
    policy: IncomeValidationPolicy,
) -> list[TransactionValidationIssue]:
    issues: list[TransactionValidationIssue] = []
    if normalize_transaction_control_code(transaction.transaction_type) != policy.transaction_type:
        issues.append(
            TransactionValidationIssue(
                code=policy.invalid_type_code,
                field="transaction_type",
                message=(
                    f"transaction_type must be {policy.transaction_type} for "
                    f"{policy.transaction_type} canonical validation."
                ),
            )
        )
    if transaction.settlement_date is None:
        issues.append(
            TransactionValidationIssue(
                code=policy.missing_settlement_code,
                field="settlement_date",
                message=f"settlement_date is required for {policy.transaction_type}.",
            )
        )
    if transaction.quantity != Decimal(0):
        issues.append(
            TransactionValidationIssue(
                code=policy.non_zero_quantity_code,
                field="quantity",
                message=f"quantity must be zero for {policy.transaction_type}.",
            )
        )
    if transaction.price != Decimal(0):
        issues.append(
            TransactionValidationIssue(
                code=policy.non_zero_price_code,
                field="price",
                message=f"price must be zero for {policy.transaction_type}.",
            )
        )
    if transaction.gross_transaction_amount <= Decimal(0):
        issues.append(
            TransactionValidationIssue(
                code=policy.non_positive_gross_code,
                field="gross_transaction_amount",
                message=(
                    "gross_transaction_amount must be greater than zero for "
                    f"{policy.transaction_type}."
                ),
            )
        )
    if not transaction.trade_currency:
        issues.append(
            TransactionValidationIssue(
                code=policy.missing_trade_currency_code,
                field="trade_currency",
                message="trade_currency is required.",
            )
        )
    if not transaction.currency:
        issues.append(
            TransactionValidationIssue(
                code=policy.missing_book_currency_code,
                field="currency",
                message="currency is required.",
            )
        )
    if (
        transaction.settlement_date is not None
        and transaction.transaction_date > transaction.settlement_date
    ):
        issues.append(
            TransactionValidationIssue(
                code=policy.invalid_date_order_code,
                field="transaction_date",
                message="transaction_date must be on or before settlement_date.",
            )
        )
    return issues


def _validate_interest_direction(
    issues: list[TransactionValidationIssue],
    transaction: BookedTransaction,
) -> None:
    if transaction.interest_direction is None:
        return
    direction = normalize_transaction_control_code(transaction.interest_direction)
    if direction not in {"INCOME", "EXPENSE"}:
        issues.append(
            TransactionValidationIssue(
                code=InterestValidationReasonCode.INVALID_INTEREST_DIRECTION,
                field="interest_direction",
                message="interest_direction must be INCOME or EXPENSE when provided.",
            )
        )


def _validate_interest_amounts(
    issues: list[TransactionValidationIssue],
    transaction: BookedTransaction,
) -> None:
    withholding_tax = transaction.withholding_tax_amount or Decimal(0)
    other_deductions = transaction.other_interest_deductions_amount or Decimal(0)
    if withholding_tax < Decimal(0):
        issues.append(
            TransactionValidationIssue(
                code=InterestValidationReasonCode.NEGATIVE_WITHHOLDING_TAX,
                field="withholding_tax_amount",
                message="withholding_tax_amount must be >= 0.",
            )
        )
    if other_deductions < Decimal(0):
        issues.append(
            TransactionValidationIssue(
                code=InterestValidationReasonCode.NEGATIVE_OTHER_DEDUCTIONS,
                field="other_interest_deductions_amount",
                message="other_interest_deductions_amount must be >= 0.",
            )
        )
    if transaction.net_interest_amount is None:
        return
    expected_net = transaction.gross_transaction_amount - withholding_tax - other_deductions
    if transaction.net_interest_amount != expected_net:
        issues.append(
            TransactionValidationIssue(
                code=InterestValidationReasonCode.NET_INTEREST_RECONCILIATION_MISMATCH,
                field="net_interest_amount",
                message=(
                    "net_interest_amount must equal gross_transaction_amount - "
                    "withholding_tax_amount - other_interest_deductions_amount."
                ),
            )
        )


def _validate_income_metadata(
    issues: list[TransactionValidationIssue],
    transaction: BookedTransaction,
    policy: IncomeValidationPolicy,
    *,
    strict_metadata: bool,
) -> None:
    if not strict_metadata:
        return
    if not transaction.economic_event_id or not transaction.linked_transaction_group_id:
        issues.append(
            TransactionValidationIssue(
                code=policy.missing_linkage_code,
                field="economic_event_id",
                message=(
                    "economic_event_id and linked_transaction_group_id are required "
                    "under strict metadata validation."
                ),
            )
        )
    if not transaction.calculation_policy_id or not transaction.calculation_policy_version:
        issues.append(
            TransactionValidationIssue(
                code=policy.missing_policy_code,
                field="calculation_policy_id",
                message=(
                    "calculation_policy_id and calculation_policy_version are required "
                    "under strict metadata validation."
                ),
            )
        )


def _validate_income_cash_entry(
    issues: list[TransactionValidationIssue],
    transaction: BookedTransaction,
    policy: IncomeValidationPolicy,
) -> None:
    if transaction.cash_entry_mode is None:
        return
    cash_entry_mode = resolve_cash_entry_mode(transaction.cash_entry_mode)
    if (
        cash_entry_mode is CashEntryMode.AUTO_GENERATE
        and not transaction.settlement_cash_account_id
    ):
        issues.append(
            TransactionValidationIssue(
                code=policy.missing_settlement_cash_account_code,
                field="settlement_cash_account_id",
                message=(
                    "settlement_cash_account_id is required when cash_entry_mode is AUTO_GENERATE."
                ),
            )
        )
    if (
        is_upstream_provided_cash_entry_mode(cash_entry_mode.value)
        and not transaction.external_cash_transaction_id
    ):
        issues.append(
            TransactionValidationIssue(
                code=policy.missing_external_cash_link_code,
                field="external_cash_transaction_id",
                message=(
                    "external_cash_transaction_id is required when "
                    "cash_entry_mode is UPSTREAM_PROVIDED."
                ),
            )
        )


_DIVIDEND_VALIDATION_POLICY = IncomeValidationPolicy(
    transaction_type="DIVIDEND",
    invalid_type_code=DividendValidationReasonCode.INVALID_TRANSACTION_TYPE,
    missing_settlement_code=DividendValidationReasonCode.MISSING_SETTLEMENT_DATE,
    non_zero_quantity_code=DividendValidationReasonCode.NON_ZERO_QUANTITY,
    non_zero_price_code=DividendValidationReasonCode.NON_ZERO_PRICE,
    non_positive_gross_code=DividendValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
    missing_trade_currency_code=DividendValidationReasonCode.MISSING_TRADE_CURRENCY,
    missing_book_currency_code=DividendValidationReasonCode.MISSING_BOOK_CURRENCY,
    invalid_date_order_code=DividendValidationReasonCode.INVALID_DATE_ORDER,
    missing_linkage_code=DividendValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
    missing_policy_code=DividendValidationReasonCode.MISSING_POLICY_METADATA,
    missing_external_cash_link_code=DividendValidationReasonCode.MISSING_EXTERNAL_CASH_LINK,
    missing_settlement_cash_account_code=(
        DividendValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT
    ),
)

_INTEREST_VALIDATION_POLICY = IncomeValidationPolicy(
    transaction_type="INTEREST",
    invalid_type_code=InterestValidationReasonCode.INVALID_TRANSACTION_TYPE,
    missing_settlement_code=InterestValidationReasonCode.MISSING_SETTLEMENT_DATE,
    non_zero_quantity_code=InterestValidationReasonCode.NON_ZERO_QUANTITY,
    non_zero_price_code=InterestValidationReasonCode.NON_ZERO_PRICE,
    non_positive_gross_code=InterestValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
    missing_trade_currency_code=InterestValidationReasonCode.MISSING_TRADE_CURRENCY,
    missing_book_currency_code=InterestValidationReasonCode.MISSING_BOOK_CURRENCY,
    invalid_date_order_code=InterestValidationReasonCode.INVALID_DATE_ORDER,
    missing_linkage_code=InterestValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
    missing_policy_code=InterestValidationReasonCode.MISSING_POLICY_METADATA,
    missing_external_cash_link_code=InterestValidationReasonCode.MISSING_EXTERNAL_CASH_LINK,
    missing_settlement_cash_account_code=(
        InterestValidationReasonCode.MISSING_SETTLEMENT_CASH_ACCOUNT
    ),
)
