"""Verify shared exact-decimal INTEREST pre-fee economics."""

from decimal import Context, Decimal, localcontext

from portfolio_common.domain.transaction.interest_economics import (
    calculate_interest_pre_fee_net,
)


def test_interest_pre_fee_net_is_independent_of_ambient_decimal_precision() -> None:
    with localcontext(Context(prec=6)):
        result = calculate_interest_pre_fee_net(
            gross_transaction_amount=Decimal("123456789.12345678"),
            withholding_tax_amount=Decimal("12345.12345678"),
            other_interest_deductions_amount=Decimal("0.00000001"),
        )

    assert result == Decimal("123444443.99999999")


def test_interest_pre_fee_net_preserves_zero_boundary() -> None:
    assert calculate_interest_pre_fee_net(
        gross_transaction_amount=Decimal("10"),
        withholding_tax_amount=Decimal("6"),
        other_interest_deductions_amount=Decimal("4"),
    ) == Decimal(0)
