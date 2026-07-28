from decimal import Decimal

import pytest
from portfolio_common.pydantic_financial_numeric import (
    ExactDecimal18_10,
    ExactNonNegativeDecimal18_10,
    ExactPositiveDecimal18_10,
)
from pydantic import BaseModel, ValidationError


class _ExactFinancialValues(BaseModel):
    signed: ExactDecimal18_10
    nonnegative: ExactNonNegativeDecimal18_10
    positive: ExactPositiveDecimal18_10


def test_exact_financial_values_accept_strings_and_lossless_integers() -> None:
    values = _ExactFinancialValues.model_validate(
        {
            "signed": "-99999999.9999999999",
            "nonnegative": 0,
            "positive": 1,
        }
    )

    assert values.signed == Decimal("-99999999.9999999999")
    assert values.nonnegative == Decimal(0)
    assert values.positive == Decimal(1)


@pytest.mark.parametrize("field_name", ["signed", "nonnegative", "positive"])
def test_exact_financial_values_reject_floating_point_input(field_name: str) -> None:
    payload: dict[str, object] = {
        "signed": "1.0000000000",
        "nonnegative": "1.0000000000",
        "positive": "1.0000000000",
    }
    payload[field_name] = 0.1

    with pytest.raises(ValidationError, match="floating-point input is not permitted"):
        _ExactFinancialValues.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "value", "violation"),
    [
        ("signed", "1.00000000001", "excess_scale"),
        ("signed", "100000000.0000000000", "magnitude_overflow"),
        ("nonnegative", "-0.0000000001", "greater than or equal to 0"),
        ("positive", "0.0000000000", "greater than 0"),
    ],
)
def test_exact_financial_values_reject_policy_violations(
    field_name: str,
    value: str,
    violation: str,
) -> None:
    payload = {
        "signed": "1.0000000000",
        "nonnegative": "1.0000000000",
        "positive": "1.0000000000",
    }
    payload[field_name] = value

    with pytest.raises(ValidationError, match=violation):
        _ExactFinancialValues.model_validate(payload)


def test_exact_financial_json_schema_does_not_advertise_floating_point_input() -> None:
    schema = _ExactFinancialValues.model_json_schema()

    assert '"type": "number"' not in str(schema)
