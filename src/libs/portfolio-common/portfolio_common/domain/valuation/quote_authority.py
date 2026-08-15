"""Product-level rules for authoritative valuation quote interpretation."""

from decimal import Decimal

from portfolio_common.domain.decimal_amount import decimal_or_none, required_decimal

BOND_QUOTE_AUTHORITY_REQUIRED_REASON = "bond valuation requires explicit quote-convention authority"


def is_quote_independent_flat_position(
    *,
    quantity: object,
    cost_basis_reporting: object,
    cost_basis_local: object,
) -> bool:
    """Return whether no quote is needed to value the position at exact zero."""

    amounts = tuple(
        decimal_or_none(value) for value in (quantity, cost_basis_reporting, cost_basis_local)
    )
    return all(amount is not None and amount == Decimal(0) for amount in amounts)


def requires_bond_quote_authority(
    *,
    product_type: str | None,
    quantity: object,
    cost_basis_reporting: object,
    cost_basis_local: object,
) -> bool:
    """Return whether a non-flat bond position requires explicit quote authority.

    A bond price's numeric magnitude cannot distinguish unit-price from
    percent-of-principal representation. Only economically flat positions remain
    quote-independent.
    """

    if _normalized_product_type(product_type) != "BOND":
        return False
    return not (
        is_quote_independent_flat_position(
            quantity=required_decimal(quantity, field_name="quantity"),
            cost_basis_reporting=required_decimal(
                cost_basis_reporting,
                field_name="cost_basis_reporting",
            ),
            cost_basis_local=required_decimal(
                cost_basis_local,
                field_name="cost_basis_local",
            ),
        )
    )


def _normalized_product_type(product_type: str | None) -> str:
    return (product_type or "").strip().upper()
