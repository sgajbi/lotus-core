"""Coordinate settlement cash-leg validation, generation, linking, and persistence."""

from dataclasses import dataclass, replace

from ...domain.transaction import (
    BookedTransaction,
    build_generated_settlement_cash_leg,
    should_generate_settlement_cash_leg,
)
from ...domain.transaction.redemption import is_generated_redemption_accrued_interest
from ...ports.settlement import (
    SettlementTransactionLookupPort,
    SettlementTransactionPersistencePort,
)
from .upstream_cash_leg import validate_upstream_cash_leg


@dataclass(frozen=True, slots=True)
class SettlementCashLegLinkingResult:
    """Return the product leg and any generated settlement cash leg."""

    product_leg: BookedTransaction
    generated_cash_leg: BookedTransaction | None


async def link_settlement_cash_leg(
    *,
    product_leg: BookedTransaction,
    transaction_lookup: SettlementTransactionLookupPort,
    transaction_persistence: SettlementTransactionPersistencePort,
) -> SettlementCashLegLinkingResult:
    """Validate or generate the product's linked settlement cash transaction."""

    if is_generated_redemption_accrued_interest(product_leg):
        return SettlementCashLegLinkingResult(product_leg=product_leg, generated_cash_leg=None)

    await validate_upstream_cash_leg(
        product_leg=product_leg,
        transactions=transaction_lookup,
    )
    if not should_generate_settlement_cash_leg(product_leg):
        return SettlementCashLegLinkingResult(
            product_leg=product_leg,
            generated_cash_leg=None,
        )

    generated_cash_leg = build_generated_settlement_cash_leg(product_leg)
    await transaction_persistence.upsert_booked_transaction(generated_cash_leg)
    linked_product_leg = replace(
        product_leg,
        external_cash_transaction_id=generated_cash_leg.transaction_id,
        economic_event_id=generated_cash_leg.economic_event_id,
        linked_transaction_group_id=generated_cash_leg.linked_transaction_group_id,
    )
    await transaction_persistence.upsert_booked_transaction(linked_product_leg)
    return SettlementCashLegLinkingResult(
        product_leg=linked_product_leg,
        generated_cash_leg=generated_cash_leg,
    )
