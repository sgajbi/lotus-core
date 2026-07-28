"""Pydantic field types for exact financial persistence boundaries."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from portfolio_common.domain.financial.precision import (
    BOUNDED_18_4_EXACT,
    BOUNDED_18_10_EXACT,
    DecimalPrecisionPolicy,
)
from pydantic import AfterValidator, ValidationInfo


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


ExactDecimal18_10 = Annotated[Decimal, AfterValidator(_require_exact_18_10)]
ExactDecimal18_4 = Annotated[Decimal, AfterValidator(_require_exact_18_4)]
