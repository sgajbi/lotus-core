"""Shared exact-decimal INTEREST economic invariants."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

INTEREST_NEGATIVE_PRE_FEE_NET_REASON_CODE = "INTEREST_018_NEGATIVE_PRE_FEE_NET"

_INTEREST_WORKING_PRECISION = 64


def calculate_interest_pre_fee_net(
    *,
    gross_transaction_amount: Decimal,
    withholding_tax_amount: Decimal | None,
    other_interest_deductions_amount: Decimal | None,
) -> Decimal:
    """Return gross interest less deductions before any transaction fee.

    The governed transaction contract persists at most 18 digits, but this helper also
    protects direct and replay callers from ambient ``Decimal`` context changes.
    """

    with localcontext(Context(prec=_INTEREST_WORKING_PRECISION, rounding=ROUND_HALF_EVEN)):
        return (
            gross_transaction_amount
            - (withholding_tax_amount or Decimal(0))
            - (other_interest_deductions_amount or Decimal(0))
        )


def has_negative_interest_pre_fee_net(
    *,
    transaction_type: str,
    gross_transaction_amount: Decimal,
    withholding_tax_amount: Decimal | None,
    other_interest_deductions_amount: Decimal | None,
) -> bool:
    """Return whether an INTEREST record has deductions greater than gross."""

    if transaction_type.strip().upper() != "INTEREST":
        return False
    return (
        calculate_interest_pre_fee_net(
            gross_transaction_amount=gross_transaction_amount,
            withholding_tax_amount=withholding_tax_amount,
            other_interest_deductions_amount=other_interest_deductions_amount,
        )
        < 0
    )
