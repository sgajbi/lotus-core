"""Original null/zero/signed source values are independently receipt-bound."""

from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.transaction.fx_source_presence import (
    FX_ORIGINAL_PNL_FIELDS,
    fx_original_pnl_values,
    fx_source_presence_input_payload,
)


def test_original_projection_preserves_all_six_values_without_rounding() -> None:
    raw = {
        name: value
        for name, value in zip(
            FX_ORIGINAL_PNL_FIELDS,
            (None, "0", "12.123456789012", "-12", None, "-0.00"),
            strict=True,
        )
    }
    original = fx_original_pnl_values(raw)
    payload = fx_source_presence_input_payload(source_values=original, booked_output={})
    assert original == dict(
        zip(
            FX_ORIGINAL_PNL_FIELDS,
            (
                None,
                Decimal("0"),
                Decimal("12.123456789012"),
                Decimal("-12"),
                None,
                Decimal("-0.00"),
            ),
            strict=True,
        )
    )
    assert payload["original_pnl"] == {
        name: {"present": value is not None, "value": value} for name, value in original.items()
    }


@pytest.mark.parametrize("name", FX_ORIGINAL_PNL_FIELDS)
def test_missing_projection_field_is_not_silently_treated_as_absent(name: str) -> None:
    values = dict.fromkeys(FX_ORIGINAL_PNL_FIELDS)
    del values[name]
    with pytest.raises(ValueError, match="missing"):
        fx_source_presence_input_payload(source_values=values, booked_output={})


@pytest.mark.parametrize("value", [False, 0, 0.0, "NaN", "Infinity", "not-numeric"])
def test_invalid_source_values_are_not_authority(value: object) -> None:
    with pytest.raises(ValueError):
        fx_original_pnl_values({"realized_fx_pnl_local": value})


def test_named_policy_original_presence_and_complete_output_are_bound() -> None:
    values = dict.fromkeys(FX_ORIGINAL_PNL_FIELDS)
    first = fx_source_presence_input_payload(source_values=values, booked_output={"tenant_id": "t"})
    first_hash = canonical_content_hash(first)
    for changed in (
        first | {"source_presence_policy": "different-policy"},
        first | {"booked_economics": {"tenant_id": "other"}},
        fx_source_presence_input_payload(
            source_values=values | {"realized_fx_pnl_local": Decimal("0")},
            booked_output={"tenant_id": "t"},
        ),
    ):
        assert canonical_content_hash(changed) != first_hash
