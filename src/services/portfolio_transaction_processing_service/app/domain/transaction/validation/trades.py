"""Validate canonical BUY and SELL booked transactions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .reason_codes import BuyValidationReasonCode, SellValidationReasonCode

TradeValidationReasonCode = BuyValidationReasonCode | SellValidationReasonCode


@dataclass(frozen=True, slots=True)
class TransactionValidationIssue:
    """Describe one deterministic transaction validation finding."""

    code: StrEnum
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class TradeValidationPolicy:
    """Bind one trade family to its stable validation reason codes."""

    transaction_type: str
    invalid_type_code: TradeValidationReasonCode
    missing_settlement_code: TradeValidationReasonCode
    non_positive_quantity_code: TradeValidationReasonCode
    non_positive_gross_code: TradeValidationReasonCode
    missing_trade_currency_code: TradeValidationReasonCode
    missing_book_currency_code: TradeValidationReasonCode
    invalid_date_order_code: TradeValidationReasonCode
    missing_linkage_code: TradeValidationReasonCode
    missing_policy_code: TradeValidationReasonCode


def validate_buy_transaction(
    transaction: BookedTransaction,
    *,
    strict_metadata: bool = False,
) -> list[TransactionValidationIssue]:
    """Return canonical BUY validation findings without mutating the transaction."""

    return _validate_trade_transaction(
        transaction,
        policy=_BUY_VALIDATION_POLICY,
        strict_metadata=strict_metadata,
    )


def validate_sell_transaction(
    transaction: BookedTransaction,
    *,
    strict_metadata: bool = False,
) -> list[TransactionValidationIssue]:
    """Return canonical SELL validation findings without mutating the transaction."""

    return _validate_trade_transaction(
        transaction,
        policy=_SELL_VALIDATION_POLICY,
        strict_metadata=strict_metadata,
    )


def _validate_trade_transaction(
    transaction: BookedTransaction,
    *,
    policy: TradeValidationPolicy,
    strict_metadata: bool,
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
    if transaction.quantity <= 0:
        issues.append(
            TransactionValidationIssue(
                code=policy.non_positive_quantity_code,
                field="quantity",
                message=f"quantity must be greater than zero for {policy.transaction_type}.",
            )
        )
    if transaction.gross_transaction_amount <= 0:
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
    if strict_metadata:
        _validate_trade_metadata(issues, transaction, policy)
    return issues


def _validate_trade_metadata(
    issues: list[TransactionValidationIssue],
    transaction: BookedTransaction,
    policy: TradeValidationPolicy,
) -> None:
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


_BUY_VALIDATION_POLICY = TradeValidationPolicy(
    transaction_type="BUY",
    invalid_type_code=BuyValidationReasonCode.INVALID_TRANSACTION_TYPE,
    missing_settlement_code=BuyValidationReasonCode.MISSING_SETTLEMENT_DATE,
    non_positive_quantity_code=BuyValidationReasonCode.NON_POSITIVE_QUANTITY,
    non_positive_gross_code=BuyValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
    missing_trade_currency_code=BuyValidationReasonCode.MISSING_TRADE_CURRENCY,
    missing_book_currency_code=BuyValidationReasonCode.MISSING_BOOK_CURRENCY,
    invalid_date_order_code=BuyValidationReasonCode.INVALID_DATE_ORDER,
    missing_linkage_code=BuyValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
    missing_policy_code=BuyValidationReasonCode.MISSING_POLICY_METADATA,
)

_SELL_VALIDATION_POLICY = TradeValidationPolicy(
    transaction_type="SELL",
    invalid_type_code=SellValidationReasonCode.INVALID_TRANSACTION_TYPE,
    missing_settlement_code=SellValidationReasonCode.MISSING_SETTLEMENT_DATE,
    non_positive_quantity_code=SellValidationReasonCode.NON_POSITIVE_QUANTITY,
    non_positive_gross_code=SellValidationReasonCode.NON_POSITIVE_GROSS_AMOUNT,
    missing_trade_currency_code=SellValidationReasonCode.MISSING_TRADE_CURRENCY,
    missing_book_currency_code=SellValidationReasonCode.MISSING_BOOK_CURRENCY,
    invalid_date_order_code=SellValidationReasonCode.INVALID_DATE_ORDER,
    missing_linkage_code=SellValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
    missing_policy_code=SellValidationReasonCode.MISSING_POLICY_METADATA,
)
