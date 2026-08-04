"""Fail-closed instrument and value-date policy for redemption commands."""

from datetime import datetime

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from .economics import REDEMPTION_TRANSACTION_TYPES

REDEMPTION_ELIGIBLE_ASSET_CLASSES = frozenset({"FIXED_INCOME"})
_TERM_REDEEMABLE_PRODUCT_TYPES = frozenset(
    {
        "ASSET_BACKED_SECURITY",
        "BOND",
        "CERTIFICATE_OF_DEPOSIT",
        "COMMERCIAL_PAPER",
        "CONVERTIBLE_BOND",
        "FIXED_INCOME",
        "MONEY_MARKET_INSTRUMENT",
        "MORTGAGE_BACKED_SECURITY",
        "NOTE",
        "STRUCTURED_CALLABLE_NOTE",
        "STRUCTURED_NOTE",
        "TREASURY_BILL",
    }
)
REDEMPTION_ELIGIBLE_PRODUCT_TYPES_BY_TRANSACTION = {
    "MATURITY_REDEMPTION": _TERM_REDEEMABLE_PRODUCT_TYPES,
    "CALL_REDEMPTION": _TERM_REDEEMABLE_PRODUCT_TYPES | {"PERPETUAL_BOND"},
    "PARTIAL_REDEMPTION": _TERM_REDEEMABLE_PRODUCT_TYPES | {"PERPETUAL_BOND"},
}


class RedemptionEligibilityError(ValueError):
    """Reject a redemption command whose instrument family cannot support it."""


def assert_redemption_command_eligible(
    *,
    transaction_type: str,
    settlement_date: datetime | None,
    product_type: str | None,
    asset_class: str | None,
) -> None:
    """Reject a redemption without authoritative value date or instrument classification."""

    normalized_transaction_type = assert_redemption_settlement_date(
        transaction_type=transaction_type,
        settlement_date=settlement_date,
    )
    if normalized_transaction_type is None:
        return
    normalized_product_type = normalize_transaction_control_code(product_type)
    normalized_asset_class = normalize_transaction_control_code(asset_class)
    eligible_products = REDEMPTION_ELIGIBLE_PRODUCT_TYPES_BY_TRANSACTION[
        normalized_transaction_type
    ]
    if normalized_product_type not in eligible_products:
        raise RedemptionEligibilityError(
            f"{normalized_transaction_type} requires an explicitly redemption-eligible "
            f"product_type; received {normalized_product_type or 'MISSING'}."
        )
    if normalized_asset_class and normalized_asset_class not in REDEMPTION_ELIGIBLE_ASSET_CLASSES:
        raise RedemptionEligibilityError(
            f"{normalized_transaction_type} requires FIXED_INCOME asset_class when supplied; "
            f"received {normalized_asset_class}."
        )


def assert_redemption_settlement_date(
    *,
    transaction_type: str,
    settlement_date: datetime | None,
) -> str | None:
    """Require source-owned value date for production redemption commands."""

    normalized_transaction_type: str = normalize_transaction_control_code(transaction_type)
    if normalized_transaction_type not in REDEMPTION_TRANSACTION_TYPES:
        return None
    if settlement_date is None:
        raise ValueError(f"settlement_date is required for {normalized_transaction_type}.")
    return normalized_transaction_type
