"""Bind original FX P/L presence separately from normalized booked economics."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

FX_ORIGINAL_PNL_PRESENCE_POLICY = "fx-original-pnl-presence@2"
FX_ORIGINAL_PNL_FIELDS = (
    "realized_capital_pnl_local",
    "realized_fx_pnl_local",
    "realized_total_pnl_local",
    "realized_capital_pnl_base",
    "realized_fx_pnl_base",
    "realized_total_pnl_base",
)


def fx_original_pnl_values(raw_source: Mapping[str, object]) -> dict[str, object]:
    """Recover six exact retained source values, never persisted defaulted amounts."""
    values: dict[str, object] = {}
    for name in FX_ORIGINAL_PNL_FIELDS:
        value = raw_source.get(name)
        if value is not None:
            if not isinstance(value, (str, Decimal)):
                raise ValueError("Original FX source amount is not exact decimal text")
            try:
                value = Decimal(value)
            except InvalidOperation:
                raise ValueError("Original FX source amount is invalid") from None
            if not value.is_finite():
                raise ValueError("Original FX source amount must be finite")
        values[name] = value
    return values


def fx_source_presence_input_payload(
    *, source_values: Mapping[str, object], booked_output: Mapping[str, object]
) -> dict[str, object]:
    """Produce the v2 input projection independently of service calculation code.

    A null original amount is not an explicit zero. Original finite Decimal values
    remain unrounded; booked economics have their existing governed output scale.
    The complete booked projection binds all unchanged inputs and derived outputs.
    This receipt does not itself confirm an absent source or revise financial values.
    """
    original: dict[str, object] = {}
    for name in FX_ORIGINAL_PNL_FIELDS:
        if name not in source_values:
            raise ValueError(f"Original FX source projection is missing {name}")
        value = source_values[name]
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            raise ValueError(f"Original FX source {name} must be a finite Decimal or null")
        original[name] = {"present": value is not None, "value": value}
    return {
        "source_presence_policy": FX_ORIGINAL_PNL_PRESENCE_POLICY,
        "original_pnl": original,
        "booked_economics": dict(booked_output),
    }
