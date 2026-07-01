"""Settlement cash-account reference policy for raw transaction persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RAW_TRANSACTION_CASH_ACCOUNT_POLICY_ID = "raw_transaction_cash_account_reference_policy_v1"
MISSING_CASH_ACCOUNT_REASON_CODE = "TRANSACTION_CASH_ACCOUNT_REFERENCE_PENDING"

CashAccountReferenceStatus = Literal[
    "not_applicable",
    "validated",
    "provisional_raw_landing",
]


@dataclass(frozen=True)
class TransactionCashAccountReferenceDecision:
    policy_id: str
    settlement_cash_account_id: str | None
    cash_account_exists: bool | None
    status: CashAccountReferenceStatus
    reason_code: str | None
    allow_raw_persistence: bool
    downstream_lifecycle_blocked: bool


def decide_transaction_cash_account_reference(
    *,
    settlement_cash_account_id: str | None,
    cash_account_exists: bool | None,
) -> TransactionCashAccountReferenceDecision:
    normalized_cash_account_id = (settlement_cash_account_id or "").strip() or None
    if normalized_cash_account_id is None:
        return TransactionCashAccountReferenceDecision(
            policy_id=RAW_TRANSACTION_CASH_ACCOUNT_POLICY_ID,
            settlement_cash_account_id=None,
            cash_account_exists=None,
            status="not_applicable",
            reason_code=None,
            allow_raw_persistence=True,
            downstream_lifecycle_blocked=False,
        )
    if cash_account_exists:
        return TransactionCashAccountReferenceDecision(
            policy_id=RAW_TRANSACTION_CASH_ACCOUNT_POLICY_ID,
            settlement_cash_account_id=normalized_cash_account_id,
            cash_account_exists=True,
            status="validated",
            reason_code=None,
            allow_raw_persistence=True,
            downstream_lifecycle_blocked=False,
        )
    return TransactionCashAccountReferenceDecision(
        policy_id=RAW_TRANSACTION_CASH_ACCOUNT_POLICY_ID,
        settlement_cash_account_id=normalized_cash_account_id,
        cash_account_exists=False,
        status="provisional_raw_landing",
        reason_code=MISSING_CASH_ACCOUNT_REASON_CODE,
        allow_raw_persistence=True,
        downstream_lifecycle_blocked=True,
    )
