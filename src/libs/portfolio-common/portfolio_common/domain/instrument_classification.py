"""Classify instruments from authoritative product metadata."""

from __future__ import annotations

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)


def is_cash_instrument(*, product_type: object, asset_class: object) -> bool:
    """Return whether server-owned instrument metadata classifies an instrument as cash."""

    authoritative_codes: set[str] = {
        str(normalize_transaction_control_code(product_type)),
        str(normalize_transaction_control_code(asset_class)),
    }
    return "CASH" in authoritative_codes
