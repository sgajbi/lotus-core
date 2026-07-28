from decimal import Decimal

import pytest
from portfolio_common.domain.financial.precision import (
    DecimalPrecisionError,
    DecimalPrecisionViolation,
)
from portfolio_common.financial_numeric import ExactNumeric
from sqlalchemy.dialects import postgresql


def _process(numeric_type: ExactNumeric, value: object) -> object:
    processor = numeric_type.bind_processor(postgresql.dialect())
    assert processor is not None
    return processor(value)


@pytest.mark.parametrize(
    ("numeric_type", "value"),
    [
        (ExactNumeric(18, 10), Decimal("99999999.9999999999")),
        (ExactNumeric(18, 4), Decimal("99999999999999.9999")),
        (ExactNumeric(), Decimal("9" * 200 + "." + "8" * 200)),
        (ExactNumeric(18, 10), 1),
    ],
)
def test_exact_numeric_accepts_exactly_representable_values(
    numeric_type: ExactNumeric,
    value: object,
) -> None:
    assert _process(numeric_type, value) is not None


@pytest.mark.parametrize(
    ("numeric_type", "value", "violation"),
    [
        (ExactNumeric(18, 10), Decimal("1.00000000001"), DecimalPrecisionViolation.EXCESS_SCALE),
        (
            ExactNumeric(18, 10),
            Decimal("100000000.0000000000"),
            DecimalPrecisionViolation.MAGNITUDE_OVERFLOW,
        ),
        (ExactNumeric(18, 4), Decimal("1.00001"), DecimalPrecisionViolation.EXCESS_SCALE),
        (
            ExactNumeric(18, 4),
            Decimal("100000000000000.0000"),
            DecimalPrecisionViolation.MAGNITUDE_OVERFLOW,
        ),
    ],
)
def test_exact_numeric_rejects_values_postgresql_would_round_or_overflow(
    numeric_type: ExactNumeric,
    value: Decimal,
    violation: DecimalPrecisionViolation,
) -> None:
    with pytest.raises(DecimalPrecisionError) as error:
        _process(numeric_type, value)

    assert error.value.violation is violation


def test_exact_numeric_rejects_undeclared_bounded_shape() -> None:
    with pytest.raises(ValueError, match="governed precision/scale policy"):
        _process(ExactNumeric(12, 2), Decimal("1.00"))
