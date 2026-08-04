"""Coordinate settlement cash-leg validation, generation, linking, and persistence."""

from dataclasses import dataclass, replace
from decimal import Decimal

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ...domain.transaction import (
    BookedTransaction,
    build_generated_settlement_cash_leg,
    resolve_cash_entry_mode,
    should_generate_settlement_cash_leg,
)
from ...domain.transaction.redemption import is_generated_redemption_accrued_interest
from ...domain.transaction.settlement import CashEntryMode
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
    reconcile_superseded_derived: bool = False,
) -> SettlementCashLegLinkingResult:
    """Validate or generate the product's linked settlement cash transaction."""

    if is_generated_redemption_accrued_interest(product_leg):
        return SettlementCashLegLinkingResult(product_leg=product_leg, generated_cash_leg=None)

    await validate_upstream_cash_leg(
        product_leg=product_leg,
        transactions=transaction_lookup,
    )
    if not should_generate_settlement_cash_leg(product_leg):
        neutralized_cash_leg = None
        if reconcile_superseded_derived:
            neutralized_cash_leg = await _neutralize_obsolete_generated_cash_leg(
                product_leg=product_leg,
                transaction_lookup=transaction_lookup,
                transaction_persistence=transaction_persistence,
            )
        if neutralized_cash_leg is not None:
            unlinked_product_leg = replace(product_leg, external_cash_transaction_id=None)
            await transaction_persistence.upsert_booked_transaction(unlinked_product_leg)
            return SettlementCashLegLinkingResult(
                product_leg=unlinked_product_leg,
                generated_cash_leg=neutralized_cash_leg,
            )
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


async def _neutralize_obsolete_generated_cash_leg(
    *,
    product_leg: BookedTransaction,
    transaction_lookup: SettlementTransactionLookupPort,
    transaction_persistence: SettlementTransactionPersistencePort,
) -> BookedTransaction | None:
    """Supersede a previously generated cash leg after its source stops generating cash."""
    cash_leg_id = f"{product_leg.transaction_id}-CASHLEG"
    existing = await transaction_lookup.get_booked_transaction(
        cash_leg_id,
        portfolio_id=product_leg.portfolio_id,
    )
    if existing is None:
        return None
    if (
        existing.transaction_id != cash_leg_id
        or normalize_transaction_control_code(existing.transaction_type) != "ADJUSTMENT"
        or existing.originating_transaction_id != product_leg.transaction_id
        or resolve_cash_entry_mode(existing.cash_entry_mode) is not CashEntryMode.AUTO_GENERATE
    ):
        raise ValueError("Existing generated cash-leg identity is inconsistent with its product.")
    neutralized = replace(existing, gross_transaction_amount=Decimal(0))
    await transaction_persistence.upsert_booked_transaction(neutralized)
    return neutralized
