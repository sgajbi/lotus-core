"""Resolve and validate upstream-provided settlement cash legs."""

from ...domain.transaction import (
    ADJUSTMENT_TRANSACTION_TYPE,
    BookedTransaction,
    assert_cash_entry_mode_supported,
    assert_upstream_cash_leg_pairing,
    is_upstream_provided_cash_entry_mode,
)
from ...ports import CostBasisTransactionStatePort


class UpstreamCashLegUnavailableError(Exception):
    """Report that a required upstream cash leg is not yet persisted."""


async def validate_upstream_cash_leg(
    *,
    product_leg: BookedTransaction,
    transactions: CostBasisTransactionStatePort,
) -> None:
    """Validate the referenced upstream cash leg when product policy requires one."""

    assert_cash_entry_mode_supported(product_leg)
    transaction_type = product_leg.transaction_type.strip().upper()
    if (
        product_leg.cash_entry_mode is None
        or not is_upstream_provided_cash_entry_mode(product_leg.cash_entry_mode)
        or transaction_type == ADJUSTMENT_TRANSACTION_TYPE
    ):
        return

    external_cash_transaction_id = (product_leg.external_cash_transaction_id or "").strip()
    if not external_cash_transaction_id:
        raise ValueError("UPSTREAM_PROVIDED requires external_cash_transaction_id on product leg.")

    cash_leg = await transactions.get_booked_transaction(
        external_cash_transaction_id,
        portfolio_id=product_leg.portfolio_id,
    )
    if cash_leg is None:
        raise UpstreamCashLegUnavailableError(
            f"Cash leg {external_cash_transaction_id} not found for portfolio "
            f"{product_leg.portfolio_id}."
        )
    assert_upstream_cash_leg_pairing(product_leg, cash_leg)
