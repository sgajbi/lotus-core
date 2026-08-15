"""Product-level rules for authoritative valuation quote interpretation."""

from decimal import Decimal

from portfolio_common.domain.decimal_amount import required_decimal

BOND_QUOTE_AUTHORITY_REQUIRED_REASON = "bond valuation requires explicit quote-convention authority"


def requires_bond_quote_authority(
    *,
    product_type: str | None,
    quantity: object,
) -> bool:
    """Return whether a non-flat bond position requires explicit quote authority.

    A bond price's numeric magnitude cannot distinguish unit-price from
    percent-of-principal representation. Zero positions remain quote-independent.
    """

    quantity_amount = required_decimal(quantity, field_name="quantity")
    return _normalized_product_type(product_type) == "BOND" and quantity_amount != Decimal(0)


def _normalized_product_type(product_type: str | None) -> str:
    return (product_type or "").strip().upper()
