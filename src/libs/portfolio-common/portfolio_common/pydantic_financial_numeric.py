"""Pydantic field types for exact financial persistence boundaries."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field, ValidationInfo

from .domain.financial.precision import (
    BOUNDED_18_4_EXACT,
    BOUNDED_18_10_EXACT,
    DecimalPrecisionPolicy,
)


def reject_floating_point_input(value: object) -> object:
    """Reject source values whose decimal representation may already be lossy."""
    if isinstance(value, float):
        raise ValueError(
            "floating-point input is not permitted for an exact financial numeric field; "
            "provide a decimal string"
        )
    return value


def _require_exact(
    value: Decimal,
    info: ValidationInfo,
    *,
    policy: DecimalPrecisionPolicy,
) -> Decimal:
    return policy.require_exact(
        value,
        field_name=info.field_name or "financial numeric field",
    )


def _require_exact_18_10(value: Decimal, info: ValidationInfo) -> Decimal:
    return _require_exact(value, info, policy=BOUNDED_18_10_EXACT)


def _require_exact_18_4(value: Decimal, info: ValidationInfo) -> Decimal:
    return _require_exact(value, info, policy=BOUNDED_18_4_EXACT)


_EXACT_DECIMAL_INPUT = BeforeValidator(
    reject_floating_point_input,
    json_schema_input_type=str | int,
)
_EXACT_RATIO_DECIMAL_INPUT = BeforeValidator(
    reject_floating_point_input,
    json_schema_input_type=str | Annotated[int, Field(ge=0, le=1)],
)
_EXACT_POSITIVE_DECIMAL_INPUT = BeforeValidator(
    reject_floating_point_input,
    json_schema_input_type=str | Annotated[int, Field(gt=0)],
)
_EXACT_NON_NEGATIVE_DECIMAL_INPUT = BeforeValidator(
    reject_floating_point_input,
    json_schema_input_type=str | Annotated[int, Field(ge=0)],
)

ExactDecimal18_10 = Annotated[
    Decimal,
    _EXACT_DECIMAL_INPUT,
    AfterValidator(_require_exact_18_10),
]
ExactDecimal18_4 = Annotated[
    Decimal,
    _EXACT_DECIMAL_INPUT,
    AfterValidator(_require_exact_18_4),
]
ExactRatioDecimal18_10 = Annotated[
    Decimal,
    Field(ge=Decimal(0), le=Decimal(1)),
    _EXACT_RATIO_DECIMAL_INPUT,
    AfterValidator(_require_exact_18_10),
]
ExactPositiveDecimal18_10 = Annotated[
    Decimal,
    Field(gt=Decimal(0)),
    _EXACT_POSITIVE_DECIMAL_INPUT,
    AfterValidator(_require_exact_18_10),
]
ExactPositiveDecimal18_4 = Annotated[
    Decimal,
    Field(gt=Decimal(0)),
    _EXACT_POSITIVE_DECIMAL_INPUT,
    AfterValidator(_require_exact_18_4),
]
ExactNonNegativeDecimal18_10 = Annotated[
    Decimal,
    Field(ge=Decimal(0)),
    _EXACT_NON_NEGATIVE_DECIMAL_INPUT,
    AfterValidator(_require_exact_18_10),
]
ExactNonNegativeDecimal18_4 = Annotated[
    Decimal,
    Field(ge=Decimal(0)),
    _EXACT_NON_NEGATIVE_DECIMAL_INPUT,
    AfterValidator(_require_exact_18_4),
]
