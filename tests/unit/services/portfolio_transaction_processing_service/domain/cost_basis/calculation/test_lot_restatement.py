"""Tests for exact cost-basis lot quantity restatement."""

from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotRestatement,
    LotRestatementError,
)


def test_restatement_applies_one_exact_ratio_to_original_and_open_quantity() -> None:
    restatement = LotRestatement.from_signed_delta(
        quantity_before=Decimal("75"),
        signed_quantity_delta=Decimal("75"),
    )

    assert restatement.apply(Decimal("100"), field_name="original_quantity") == Decimal(
        "200.0000000000"
    )
    assert restatement.apply(Decimal("75"), field_name="open_quantity") == Decimal("150.0000000000")
    assert restatement.lineage_payload() == {
        "quantity_before": Decimal("75"),
        "quantity_after": Decimal("150"),
        "factor_numerator": Decimal("150"),
        "factor_denominator": Decimal("75"),
    }


def test_restatement_supports_an_exact_repeating_ratio_without_rounding_factor() -> None:
    restatement = LotRestatement(
        quantity_before=Decimal("3"),
        quantity_after=Decimal("4"),
    )

    assert restatement.apply(Decimal("3"), field_name="open_quantity") == Decimal("4.0000000000")


def test_restatement_rejects_non_representable_source_quantity() -> None:
    restatement = LotRestatement(
        quantity_before=Decimal("3"),
        quantity_after=Decimal("4"),
    )

    with pytest.raises(
        LotRestatementError,
        match="cannot be restated exactly at 10 decimal places",
    ):
        restatement.apply(Decimal("1"), field_name="open_quantity")


def test_restatement_maps_storage_overflow_to_stable_domain_failure() -> None:
    with pytest.raises(
        LotRestatementError,
        match="quantity_after exceeds governed quantity precision",
    ):
        LotRestatement.from_signed_delta(
            quantity_before=Decimal("99999999"),
            signed_quantity_delta=Decimal("99999999"),
        )


@pytest.mark.parametrize(
    ("quantity_before", "signed_delta", "match"),
    [
        (Decimal("0"), Decimal("1"), "quantity_before must be positive"),
        (Decimal("10"), Decimal("-10"), "quantity_after must be positive"),
        (Decimal("10"), Decimal("-11"), "quantity_after must be non-negative"),
        (Decimal("10"), Decimal("0"), "lot restatement must change quantity"),
    ],
)
def test_restatement_rejects_non_economic_book_transitions(
    quantity_before: Decimal,
    signed_delta: Decimal,
    match: str,
) -> None:
    with pytest.raises(LotRestatementError, match=match):
        LotRestatement.from_signed_delta(
            quantity_before=quantity_before,
            signed_quantity_delta=signed_delta,
        )
