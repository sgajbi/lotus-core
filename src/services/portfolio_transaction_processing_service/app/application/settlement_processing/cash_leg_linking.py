"""Coordinate settlement cash-leg validation, generation, linking, and persistence."""

from dataclasses import dataclass, replace
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.transaction.fee_components import TRANSACTION_FEE_COMPONENT_FIELDS
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)
from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ...domain.transaction import (
    BookedTransaction,
    build_generated_settlement_cash_leg,
    build_transaction_semantic_identity,
    resolve_cash_entry_mode,
    should_generate_settlement_cash_leg,
)
from ...domain.transaction.redemption import is_generated_redemption_accrued_interest
from ...domain.transaction.settlement import CashEntryMode
from ...ports import CostBasisFxRatePort
from ...ports.settlement import (
    SettlementTransactionLookupPort,
    SettlementTransactionPersistencePort,
)
from ..errors import FxRateNotFoundError, TransactionProcessingRejected
from ..fx_rate_selection import select_latest_effective_fx_rate
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
    derive_fx_at_settlement: bool = False,
    portfolio_base_currency: str | None = None,
    fx_rates: CostBasisFxRatePort | None = None,
    settlement_cash_currency: str | None = None,
    resolved_settlement_cash_instrument_id: str | None = None,
) -> SettlementCashLegLinkingResult:
    """Validate or generate the product's linked settlement cash transaction."""

    trade_currency = str(product_leg.trade_currency or "").strip().upper()
    base_currency = str(portfolio_base_currency or "").strip().upper()
    if (
        trade_currency
        and base_currency
        and trade_currency == base_currency
        and product_leg.transaction_fx_rate not in (None, Decimal(1))
    ):
        raise TransactionProcessingRejected(
            reason_code="same_currency_fx_rate_invalid",
            detail={
                "transaction_id": product_leg.transaction_id,
                "currency": trade_currency,
                "transaction_fx_rate": str(product_leg.transaction_fx_rate),
            },
            retryable=False,
        )

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
            await transaction_persistence.upsert_booked_transaction(
                unlinked_product_leg,
                fields_to_clear=frozenset({"external_cash_transaction_id"}),
            )
            return SettlementCashLegLinkingResult(
                product_leg=unlinked_product_leg,
                generated_cash_leg=neutralized_cash_leg,
            )
        return SettlementCashLegLinkingResult(
            product_leg=product_leg,
            generated_cash_leg=None,
        )

    generated_cash_leg_id = f"{product_leg.transaction_id}-CASHLEG"
    preserves_linked_generated_leg = (
        not reconcile_superseded_derived
        and product_leg.external_cash_transaction_id == generated_cash_leg_id
    )
    existing_generated_cash_leg = None
    if preserves_linked_generated_leg or derive_fx_at_settlement:
        existing_generated_cash_leg = await transaction_lookup.get_booked_transaction(
            generated_cash_leg_id,
            portfolio_id=product_leg.portfolio_id,
        )
        if (
            preserves_linked_generated_leg
            and existing_generated_cash_leg is None
            and (
                trade_currency != base_currency
                or not str(product_leg.settlement_cash_instrument_id or "").strip()
            )
        ):
            raise FxRateNotFoundError(
                f"Booked generated settlement FX for {generated_cash_leg_id} is unavailable. "
                "Retrying..."
            )

    authoritative_cash_currency = (
        str(
            settlement_cash_currency
            or (
                existing_generated_cash_leg.trade_currency
                if existing_generated_cash_leg is not None
                else None
            )
            or ""
        )
        .strip()
        .upper()
    )
    if authoritative_cash_currency and authoritative_cash_currency != trade_currency:
        raise TransactionProcessingRejected(
            reason_code="settlement_cash_currency_mismatch",
            detail={
                "transaction_id": product_leg.transaction_id,
                "trade_currency": trade_currency,
                "settlement_cash_currency": authoritative_cash_currency,
            },
            retryable=False,
        )

    generated_fx_rate = product_leg.transaction_fx_rate
    if derive_fx_at_settlement or preserves_linked_generated_leg:
        generated_fx_rate = await _resolve_generated_cash_leg_fx_rate(
            product_leg=product_leg,
            existing_generated_cash_leg=existing_generated_cash_leg,
            preserve_existing=(
                not reconcile_superseded_derived
                and (derive_fx_at_settlement or preserves_linked_generated_leg)
            ),
            derive_from_reference=derive_fx_at_settlement,
            portfolio_base_currency=portfolio_base_currency,
            fx_rates=fx_rates,
        )
    generated_cash_leg = build_generated_settlement_cash_leg(
        replace(
            product_leg,
            transaction_fx_rate=generated_fx_rate,
            settlement_cash_instrument_id=(
                resolved_settlement_cash_instrument_id
                or (
                    existing_generated_cash_leg.security_id
                    if existing_generated_cash_leg is not None
                    else None
                )
                or product_leg.settlement_cash_instrument_id
            ),
        )
    )
    generated_cash_leg = await _persist_generated_cash_leg(
        proposed=generated_cash_leg,
        product_leg=product_leg,
        transaction_persistence=transaction_persistence,
    )
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


async def _resolve_generated_cash_leg_fx_rate(
    *,
    product_leg: BookedTransaction,
    existing_generated_cash_leg: BookedTransaction | None,
    preserve_existing: bool,
    derive_from_reference: bool,
    portfolio_base_currency: str | None,
    fx_rates: CostBasisFxRatePort | None,
) -> Decimal | None:
    cash_leg_id = f"{product_leg.transaction_id}-CASHLEG"
    if preserve_existing and existing_generated_cash_leg is not None:
        if existing_generated_cash_leg.transaction_fx_rate is not None:
            return Decimal(existing_generated_cash_leg.transaction_fx_rate)

    if not derive_from_reference:
        trade_currency = str(product_leg.trade_currency or "").strip().upper()
        base_currency = str(portfolio_base_currency or "").strip().upper()
        if trade_currency and base_currency and trade_currency == base_currency:
            return Decimal(1)
        raise FxRateNotFoundError(
            f"Booked generated settlement FX for {cash_leg_id} is unavailable. Retrying..."
        )

    trade_currency = str(product_leg.trade_currency or "").strip().upper()
    base_currency = str(portfolio_base_currency or "").strip().upper()
    if not base_currency or fx_rates is None:
        raise ValueError(
            "Settlement-date FX derivation requires portfolio base currency and FX rate port."
        )
    if trade_currency == base_currency:
        return Decimal(1)

    settlement_at = product_leg.settlement_date or product_leg.transaction_date
    settlement_date = settlement_at.date()
    rate_window = await fx_rates.get_fx_rate_window(
        from_currency=trade_currency,
        to_currency=base_currency,
        start_date=settlement_date,
        end_date=settlement_date,
    )
    effective_rate = select_latest_effective_fx_rate(rate_window, settlement_date)
    if effective_rate is None:
        raise FxRateNotFoundError(
            f"FX rate for {trade_currency}->{base_currency} on {settlement_date} not found. "
            "Retrying..."
        )
    return Decimal(effective_rate.rate)


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
    zero = Decimal(0)
    lineage = build_calculation_lineage(
        algorithm_id="generated-settlement-cash-neutralization",
        algorithm_version=1,
        intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
        input_payload={
            "corrected_source": {
                **_neutralization_transaction_snapshot(product_leg),
                "calculation_lineage": (
                    product_leg.calculation_lineage.lineage_payload()
                    if product_leg.calculation_lineage is not None
                    else None
                ),
            },
            "prior_cash_leg": {
                **_neutralization_transaction_snapshot(existing),
                "calculation_lineage": (
                    existing.calculation_lineage.lineage_payload()
                    if existing.calculation_lineage is not None
                    else None
                ),
            },
        },
        output_payload={
            "transaction_id": existing.transaction_id,
            "gross_transaction_amount": zero,
            "gross_cost": zero,
            "net_cost": zero,
            "net_cost_local": zero,
            "realized_gain_loss": zero,
            "realized_gain_loss_local": zero,
        },
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    )
    neutralized = replace(
        existing,
        gross_transaction_amount=zero,
        gross_cost=zero,
        net_cost=zero,
        net_cost_local=zero,
        realized_gain_loss=zero,
        realized_gain_loss_local=zero,
        calculation_lineage=lineage,
    )
    return await _persist_generated_cash_leg(
        proposed=neutralized,
        product_leg=product_leg,
        transaction_persistence=transaction_persistence,
    )


async def _persist_generated_cash_leg(
    *,
    proposed: BookedTransaction,
    product_leg: BookedTransaction,
    transaction_persistence: SettlementTransactionPersistencePort,
) -> BookedTransaction:
    """Carry the exact canonical upsert result without inventing financial defaults."""
    persisted = await transaction_persistence.upsert_generated_booked_transaction(proposed)
    if not isinstance(persisted, BookedTransaction):
        raise ValueError("Generated cash persistence returned no canonical authority")
    if (
        persisted.transaction_id != proposed.transaction_id
        or persisted.portfolio_id != product_leg.portfolio_id
        or persisted.security_id != proposed.security_id
        or persisted.tenant_id != proposed.tenant_id
    ):
        raise ValueError("Generated cash persistence returned conflicting source scope")
    # Epoch is admitted command context, not an ORM column or latest-row inference.
    persisted = replace(persisted, epoch=product_leg.epoch)
    expected = replace(proposed, epoch=product_leg.epoch)
    if build_transaction_semantic_identity(persisted) != (
        build_transaction_semantic_identity(expected)
    ):
        raise ValueError("Generated cash persistence returned conflicting material identity")
    comparable = replace(
        persisted,
        created_at=expected.created_at,
        calculation_policy_id=expected.calculation_policy_id,
        calculation_policy_version=expected.calculation_policy_version,
        cash_entry_mode=expected.cash_entry_mode,
        external_cash_transaction_id=expected.external_cash_transaction_id,
        economic_event_id=expected.economic_event_id,
        linked_transaction_group_id=expected.linked_transaction_group_id,
    )
    # A generated cash constructor does not calculate these P&L columns. Retain
    # their actual stored facts; an explicit neutralization value must still match.
    comparable = replace(
        comparable,
        realized_gain_loss=(
            None if expected.realized_gain_loss is None else comparable.realized_gain_loss
        ),
        realized_gain_loss_local=(
            None
            if expected.realized_gain_loss_local is None
            else comparable.realized_gain_loss_local
        ),
    )
    if comparable != expected:
        raise ValueError("Generated cash persistence returned conflicting effects or lineage")
    return persisted


def _neutralization_transaction_snapshot(transaction: BookedTransaction) -> dict[str, object]:
    """Bind the durable economics and authority of a corrected or derived leg."""

    return {
        "transaction_id": transaction.transaction_id,
        "transaction_type": normalize_transaction_control_code(transaction.transaction_type),
        "transaction_date": transaction.transaction_date.isoformat(),
        "settlement_date": (
            transaction.settlement_date.isoformat()
            if transaction.settlement_date is not None
            else None
        ),
        "tenant_id": transaction.tenant_id,
        "portfolio_id": transaction.portfolio_id,
        "security_id": transaction.security_id,
        "cash_entry_mode": transaction.cash_entry_mode,
        "gross_transaction_amount": transaction.gross_transaction_amount,
        "gross_cost": transaction.gross_cost,
        "net_cost": transaction.net_cost,
        "net_cost_local": transaction.net_cost_local,
        "realized_gain_loss": transaction.realized_gain_loss,
        "realized_gain_loss_local": transaction.realized_gain_loss_local,
        "fee_components": {
            field: getattr(transaction, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS
        },
        "withholding_tax_amount": transaction.withholding_tax_amount,
        "other_interest_deductions_amount": transaction.other_interest_deductions_amount,
        "net_interest_amount": transaction.net_interest_amount,
        "principal_proceeds_local": transaction.principal_proceeds_local,
        "accrued_interest_proceeds_local": transaction.accrued_interest_proceeds_local,
        "embedded_fee_amount_local": transaction.embedded_fee_amount_local,
        "embedded_tax_amount_local": transaction.embedded_tax_amount_local,
        "trade_currency": transaction.trade_currency,
        "currency": transaction.currency,
        "transaction_fx_rate": transaction.transaction_fx_rate,
        "transaction_fx_rate_origin": transaction.transaction_fx_rate_origin,
        "settlement_cash_account_id": transaction.settlement_cash_account_id,
        "settlement_cash_instrument_id": transaction.settlement_cash_instrument_id,
        "economic_event_id": transaction.economic_event_id,
        "linked_transaction_group_id": transaction.linked_transaction_group_id,
        "originating_transaction_id": transaction.originating_transaction_id,
        "originating_transaction_type": transaction.originating_transaction_type,
    }
