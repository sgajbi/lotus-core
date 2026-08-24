"""Transaction-domain compatibility import for shared instrument classification."""

from __future__ import annotations

from portfolio_common.domain.instrument_classification import (
    is_cash_instrument as _is_cash_instrument,
)


def is_cash_instrument(*, product_type: object, asset_class: object) -> bool:
    """Return the shared metadata-only cash classification with a typed service boundary."""

    return bool(_is_cash_instrument(product_type=product_type, asset_class=asset_class))


__all__ = ["is_cash_instrument"]
