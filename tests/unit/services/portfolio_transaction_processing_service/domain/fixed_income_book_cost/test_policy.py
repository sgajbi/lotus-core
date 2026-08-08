"""Tests for governed fixed-income amortized-cost policy vocabulary."""

from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    AmortizedCostDirection,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    YieldApplicationConvention,
    classify_amortized_cost_direction,
)


def _policy(**overrides: object) -> AmortizedCostPolicy:
    values: dict[str, object] = {
        "policy_id": "FI_EIR_BOOK_COST",
        "policy_version": 1,
        "method": AmortizedCostMethod.EFFECTIVE_YIELD,
        "yield_application_convention": YieldApplicationConvention.ANNUAL_EFFECTIVE,
        "include_fees_in_amortized_cost": True,
        "residual_tolerance_local": Decimal("0.01"),
    }
    values.update(overrides)
    return AmortizedCostPolicy(**values)  # type: ignore[arg-type]


def test_policy_normalizes_identity_and_retains_explicit_yield_convention() -> None:
    policy = _policy(policy_id="  FI_EIR_BOOK_COST  ")

    assert policy.policy_id == "FI_EIR_BOOK_COST"
    assert policy.yield_application_convention is YieldApplicationConvention.ANNUAL_EFFECTIVE


def test_rfc_effective_yield_vocabulary_deserializes_without_translation() -> None:
    assert AmortizedCostMethod("EFFECTIVE_YIELD") is AmortizedCostMethod.EFFECTIVE_YIELD


@pytest.mark.parametrize(
    ("field_name", "value", "expected_error", "message"),
    [
        ("policy_id", None, TypeError, "must be a string"),
        ("policy_id", "   ", ValueError, "must be nonblank"),
        ("policy_version", True, TypeError, "must be an integer"),
        ("policy_version", 0, ValueError, "must be positive"),
        ("method", "EFFECTIVE_YIELD", TypeError, "must be an AmortizedCostMethod"),
        (
            "yield_application_convention",
            "ANNUAL_EFFECTIVE",
            TypeError,
            "must be a YieldApplicationConvention or None",
        ),
        (
            "include_fees_in_amortized_cost",
            1,
            TypeError,
            "must be a boolean",
        ),
        (
            "residual_tolerance_local",
            Decimal("NaN"),
            ValueError,
            "must be finite",
        ),
        (
            "residual_tolerance_local",
            Decimal("-0.01"),
            ValueError,
            "must be nonnegative",
        ),
    ],
)
def test_policy_rejects_malformed_or_unsafe_fields(
    field_name: str,
    value: object,
    expected_error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(expected_error, match=message):
        _policy(**{field_name: value})


def test_effective_yield_requires_explicit_yield_convention() -> None:
    with pytest.raises(ValueError, match="requires a yield convention"):
        _policy(yield_application_convention=None)


def test_straight_line_rejects_inapplicable_yield_convention() -> None:
    with pytest.raises(ValueError, match="must not declare"):
        _policy(method=AmortizedCostMethod.STRAIGHT_LINE)

    policy = _policy(
        method=AmortizedCostMethod.STRAIGHT_LINE,
        yield_application_convention=None,
    )
    assert policy.method is AmortizedCostMethod.STRAIGHT_LINE


@pytest.mark.parametrize(
    ("opening", "redemption", "expected"),
    [
        ("105", "100", AmortizedCostDirection.PREMIUM_AMORTIZATION),
        ("92", "100", AmortizedCostDirection.DISCOUNT_ACCRETION),
        ("100", "100", AmortizedCostDirection.AT_PAR),
    ],
)
def test_direction_is_derived_from_book_cost_and_redemption_value(
    opening: str,
    redemption: str,
    expected: AmortizedCostDirection,
) -> None:
    assert (
        classify_amortized_cost_direction(
            opening_amortized_cost_local=Decimal(opening),
            redemption_value_local=Decimal(redemption),
        )
        is expected
    )


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_direction_rejects_nonfinite_or_negative_book_values(value: Decimal) -> None:
    with pytest.raises(ValueError):
        classify_amortized_cost_direction(
            opening_amortized_cost_local=value,
            redemption_value_local=Decimal("100"),
        )
