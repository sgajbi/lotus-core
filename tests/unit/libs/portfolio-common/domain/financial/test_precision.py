from decimal import Decimal

import pytest
from portfolio_common.domain.financial.precision import (
    BOUNDED_18_4_EXACT,
    BOUNDED_18_10_EXACT,
    EXACT_UNBOUNDED,
    DecimalPrecisionError,
    DecimalPrecisionPolicy,
    DecimalPrecisionViolation,
)


@pytest.mark.parametrize(
    "value",
    [
        Decimal("0"),
        Decimal("-0E-100"),
        Decimal("99999999.9999999999"),
        Decimal("-99999999.9999999999"),
        Decimal("1.23000000000"),
        Decimal("1E-10"),
    ],
)
def test_bounded_policy_accepts_exact_18_10_values(value: Decimal) -> None:
    assert BOUNDED_18_10_EXACT.require_exact(value, field_name="amount") is value


@pytest.mark.parametrize(
    ("value", "violation"),
    [
        (Decimal("1.00000000001"), DecimalPrecisionViolation.EXCESS_SCALE),
        (Decimal("1E-11"), DecimalPrecisionViolation.EXCESS_SCALE),
        (Decimal("100000000"), DecimalPrecisionViolation.MAGNITUDE_OVERFLOW),
        (Decimal("-100000000"), DecimalPrecisionViolation.MAGNITUDE_OVERFLOW),
        (Decimal("NaN"), DecimalPrecisionViolation.NON_FINITE),
        (Decimal("Infinity"), DecimalPrecisionViolation.NON_FINITE),
        (Decimal("-Infinity"), DecimalPrecisionViolation.NON_FINITE),
    ],
)
def test_bounded_policy_rejects_non_representable_values(
    value: Decimal,
    violation: DecimalPrecisionViolation,
) -> None:
    with pytest.raises(DecimalPrecisionError) as exc_info:
        BOUNDED_18_10_EXACT.require_exact(value, field_name="amount")

    assert exc_info.value.field_name == "amount"
    assert exc_info.value.policy_name == "bounded-18-10-exact"
    assert exc_info.value.violation is violation
    assert str(value) not in str(exc_info.value)


def test_bounded_18_4_policy_uses_four_fractional_and_fourteen_integer_digits() -> None:
    assert BOUNDED_18_4_EXACT.require_exact(
        Decimal("99999999999999.9999"),
        field_name="threshold_amount",
    ) == Decimal("99999999999999.9999")

    with pytest.raises(DecimalPrecisionError) as scale_error:
        BOUNDED_18_4_EXACT.require_exact(
            Decimal("1.00001"),
            field_name="threshold_amount",
        )
    assert scale_error.value.violation is DecimalPrecisionViolation.EXCESS_SCALE

    with pytest.raises(DecimalPrecisionError) as magnitude_error:
        BOUNDED_18_4_EXACT.require_exact(
            Decimal("100000000000000"),
            field_name="threshold_amount",
        )
    assert magnitude_error.value.violation is DecimalPrecisionViolation.MAGNITUDE_OVERFLOW


def test_unbounded_policy_preserves_arbitrary_finite_decimal() -> None:
    value = Decimal(f"{'9' * 200}.{'1' * 200}")

    assert EXACT_UNBOUNDED.require_exact(value, field_name="source_price") is value


@pytest.mark.parametrize(
    ("precision", "scale"),
    [
        (None, 10),
        (18, None),
        (0, 0),
        (4, -1),
        (4, 5),
    ],
)
def test_policy_definition_rejects_incoherent_shapes(
    precision: int | None,
    scale: int | None,
) -> None:
    with pytest.raises(ValueError):
        DecimalPrecisionPolicy(name="invalid", precision=precision, scale=scale)


def test_policy_definition_requires_name() -> None:
    with pytest.raises(ValueError, match="name is required"):
        DecimalPrecisionPolicy(name="", precision=18, scale=10)
