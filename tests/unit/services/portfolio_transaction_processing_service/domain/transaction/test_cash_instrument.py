"""Prove cash-instrument classification uses source-owned product metadata only."""

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    is_cash_instrument,
)


@pytest.mark.parametrize(
    ("product_type", "asset_class"),
    [
        ("CASH", None),
        (None, "Cash"),
        (" cash ", "currency"),
        ("currency", " cash "),
    ],
)
def test_cash_instrument_accepts_normalized_authoritative_metadata(
    product_type: str | None,
    asset_class: str | None,
) -> None:
    assert is_cash_instrument(product_type=product_type, asset_class=asset_class)


@pytest.mark.parametrize(
    ("product_type", "asset_class"),
    [
        ("EQUITY", "EQUITY"),
        ("BOND", "FIXED_INCOME"),
        (None, None),
        ("", " "),
    ],
)
def test_cash_instrument_rejects_non_cash_or_missing_authority(
    product_type: str | None,
    asset_class: str | None,
) -> None:
    assert not is_cash_instrument(product_type=product_type, asset_class=asset_class)


def test_cash_instrument_cannot_be_inferred_from_identifier_shaped_metadata() -> None:
    assert not is_cash_instrument(
        product_type="CASH_USD",
        asset_class="CASH_ACCOUNT_001",
    )
