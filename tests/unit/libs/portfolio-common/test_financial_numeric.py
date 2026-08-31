from decimal import Decimal

import pytest
from portfolio_common.domain.financial.precision import (
    DecimalPrecisionError,
    DecimalPrecisionViolation,
)
from portfolio_common.financial_numeric import ExactNumeric, finite_numeric_check_constraint
from sqlalchemy import literal, select
from sqlalchemy.dialects import postgresql, sqlite


def _process(numeric_type: ExactNumeric, value: object) -> object:
    processor = numeric_type.bind_processor(postgresql.dialect())
    assert processor is not None
    return processor(value)


def test_finite_numeric_check_constraint_is_bounded_and_injection_safe() -> None:
    constraint = finite_numeric_check_constraint("ck_amount_finite", "amount", "cost_basis")

    assert constraint.name == "ck_amount_finite"
    assert str(constraint.sqltext) == (
        "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') AND "
        "CAST(cost_basis AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
    )
    with pytest.raises(ValueError, match="at least one"):
        finite_numeric_check_constraint("ck_empty")
    with pytest.raises(ValueError, match="identifiers"):
        finite_numeric_check_constraint("ck_unsafe", "amount); DROP TABLE portfolios; --")


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


def test_exact_numeric_requires_decimal_result_semantics() -> None:
    with pytest.raises(ValueError, match="requires Decimal result semantics"):
        ExactNumeric(18, 10, asdecimal=False)


def test_exact_numeric_fails_closed_for_non_postgresql_persistence() -> None:
    processor = ExactNumeric(18, 10).bind_processor(sqlite.dialect())
    assert processor is not None

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        processor(Decimal("1.0000000000"))


def test_exact_numeric_supports_generic_compile_only_literal_rendering() -> None:
    statement = select(literal(Decimal("1.0000000000"), type_=ExactNumeric(18, 10)))

    assert "1.0000000000" in str(statement.compile(compile_kwargs={"literal_binds": True}))
