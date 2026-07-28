from decimal import Decimal, getcontext

import pytest
from portfolio_common.domain.financial.calculation_precision import (
    CalculatedDecimalPolicy,
)
from portfolio_common.domain.financial.precision import (
    DecimalPrecisionError,
    DecimalPrecisionViolation,
)

POLICY = CalculatedDecimalPolicy(
    name="test-calculated-ledger-output",
    version="1.0.0",
    precision=18,
    scale=10,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.00000000004", "1.0000000000"),
        ("1.00000000005", "1.0000000000"),
        ("1.00000000015", "1.0000000002"),
        ("-1.00000000015", "-1.0000000002"),
    ],
)
def test_calculated_policy_uses_deterministic_half_even_normalization(
    value: str,
    expected: str,
) -> None:
    assert POLICY.normalize(Decimal(value), field_name="amount") == Decimal(expected)


def test_calculated_policy_preserves_exact_value_representation() -> None:
    value = Decimal("1200.00")

    result = POLICY.normalize(value, field_name="amount")

    assert result.as_tuple() == value.as_tuple()


def test_calculated_policy_uses_explicit_working_precision_for_products() -> None:
    original_precision = getcontext().prec
    try:
        getcontext().prec = 12

        result = POLICY.multiply(
            Decimal("12345678.1234567890"),
            Decimal("0.1234567890"),
            field_name="market_value",
        )

        assert result == Decimal("1524157.7791495208")
        assert getcontext().prec == 12
    finally:
        getcontext().prec = original_precision


def test_calculated_policy_rounds_repeating_division_once_at_output_boundary() -> None:
    assert POLICY.divide(
        Decimal("100"),
        Decimal("3"),
        field_name="average_cost",
    ) == Decimal("33.3333333333")


def test_calculated_policy_rejects_post_rounding_magnitude_overflow() -> None:
    with pytest.raises(DecimalPrecisionError) as exc_info:
        POLICY.normalize(
            Decimal("99999999.99999999996"),
            field_name="amount",
        )

    assert exc_info.value.violation is DecimalPrecisionViolation.MAGNITUDE_OVERFLOW
    assert exc_info.value.policy_name == "test-calculated-ledger-output@1.0.0"


def test_calculated_policy_rejects_non_finite_values() -> None:
    with pytest.raises(DecimalPrecisionError) as exc_info:
        POLICY.normalize(Decimal("NaN"), field_name="amount")

    assert exc_info.value.violation is DecimalPrecisionViolation.NON_FINITE


def test_calculated_policy_rejects_insufficient_working_precision() -> None:
    with pytest.raises(ValueError, match="at least twice storage precision"):
        CalculatedDecimalPolicy(
            name="invalid",
            version="1.0.0",
            precision=18,
            scale=10,
            working_precision=35,
        )
