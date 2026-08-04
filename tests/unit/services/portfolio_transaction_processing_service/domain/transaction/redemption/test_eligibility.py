"""Verify fail-closed redemption instrument and value-date eligibility."""

from datetime import UTC, datetime

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import redemption

VALUE_DATE = datetime(2026, 8, 6, tzinfo=UTC)


@pytest.mark.parametrize(
    "transaction_type",
    ["MATURITY_REDEMPTION", "CALL_REDEMPTION", "PARTIAL_REDEMPTION"],
)
def test_redemption_accepts_explicit_fixed_income_product_family(
    transaction_type: str,
) -> None:
    redemption.assert_redemption_command_eligible(
        transaction_type=transaction_type,
        settlement_date=VALUE_DATE,
        product_type=" bond ",
        asset_class=" fixed_income ",
    )


@pytest.mark.parametrize(
    ("product_type", "asset_class"),
    [
        ("EQUITY", "EQUITY"),
        ("EQUITY", "FIXED_INCOME"),
        ("BOND", "EQUITY"),
        ("STRUCTURED_PRODUCT", "FIXED_INCOME"),
        (None, None),
    ],
)
def test_redemption_rejects_missing_or_contradictory_product_classification(
    product_type: str | None,
    asset_class: str | None,
) -> None:
    with pytest.raises(redemption.RedemptionEligibilityError):
        redemption.assert_redemption_command_eligible(
            transaction_type="MATURITY_REDEMPTION",
            settlement_date=VALUE_DATE,
            product_type=product_type,
            asset_class=asset_class,
        )


def test_perpetual_bond_is_callable_but_has_no_maturity_redemption() -> None:
    with pytest.raises(redemption.RedemptionEligibilityError):
        redemption.assert_redemption_command_eligible(
            transaction_type="MATURITY_REDEMPTION",
            settlement_date=VALUE_DATE,
            product_type="PERPETUAL_BOND",
            asset_class="FIXED_INCOME",
        )

    redemption.assert_redemption_command_eligible(
        transaction_type="CALL_REDEMPTION",
        settlement_date=VALUE_DATE,
        product_type="PERPETUAL_BOND",
        asset_class="FIXED_INCOME",
    )


def test_non_redemption_is_outside_redemption_eligibility_policy() -> None:
    redemption.assert_redemption_command_eligible(
        transaction_type="SELL",
        settlement_date=None,
        product_type="EQUITY",
        asset_class="EQUITY",
    )
