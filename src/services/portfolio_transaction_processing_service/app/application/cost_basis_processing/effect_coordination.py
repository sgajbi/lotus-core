"""Coordinate settlement, reconciliation, and staging for processed cost effects."""

from collections.abc import Sequence
from dataclasses import replace

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import FxContractInstrument
from ...domain.transaction.redemption import (
    REDEMPTION_TRANSACTION_TYPES,
    build_redemption_accrued_interest_component,
    neutralize_generated_redemption_accrued_interest,
    redemption_accrued_interest_transaction_id,
)
from ...ports import (
    CorporateActionReconciliationObserver,
    CorporateActionReconciliationRepository,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
)
from ..corporate_action_reconciliation import CorporateActionReconciliationCoordinator
from ..settlement_processing import link_settlement_cash_leg


async def coordinate_cost_processing_effects(
    *,
    tenant_id: str,
    processed_transactions: Sequence[BookedTransaction],
    instrument_updates: Sequence[FxContractInstrument],
    source_epoch: int | None,
    transaction_state: CostBasisTransactionStatePort,
    reconciliation_repository: CorporateActionReconciliationRepository,
    effect_stager: CostProcessingEffectStagingPort,
    correlation_id: str,
    corrected_transaction_id: str | None = None,
    reconciliation_observer: CorporateActionReconciliationObserver | None = None,
) -> CostProcessingResult:
    """Link settlement, reconcile corporate actions, and stage domain-valued effects."""

    emitted_transactions: list[BookedTransaction] = []
    reconciliation = CorporateActionReconciliationCoordinator(
        reconciliation_repository,
        observer=reconciliation_observer,
    )
    for processed_transaction in processed_transactions:
        linking = await link_settlement_cash_leg(
            product_leg=processed_transaction,
            transaction_lookup=transaction_state,
            transaction_persistence=transaction_state,
            reconcile_superseded_derived=(
                processed_transaction.transaction_id == corrected_transaction_id
            ),
        )
        await reconciliation.reconcile(
            linking.product_leg,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        emitted_transactions.append(
            _with_source_epoch(linking.product_leg, source_epoch=source_epoch)
        )
        accrued_interest = build_redemption_accrued_interest_component(linking.product_leg)
        transaction_type = normalize_transaction_control_code(linking.product_leg.transaction_type)
        reconcile_prior_interest = (
            transaction_type in REDEMPTION_TRANSACTION_TYPES
            or linking.product_leg.transaction_id == corrected_transaction_id
        )
        prior_interest = None
        correction_requires_prior_interest = (
            linking.product_leg.transaction_id == corrected_transaction_id
        )
        if reconcile_prior_interest and (
            accrued_interest is None or correction_requires_prior_interest
        ):
            prior_interest = await transaction_state.get_booked_transaction(
                redemption_accrued_interest_transaction_id(linking.product_leg.transaction_id),
                portfolio_id=linking.product_leg.portfolio_id,
            )
            if prior_interest is not None:
                accrued_interest = (
                    build_redemption_accrued_interest_component(
                        linking.product_leg,
                        include_zero=True,
                    )
                    if transaction_type in REDEMPTION_TRANSACTION_TYPES
                    else neutralize_generated_redemption_accrued_interest(
                        prior_interest,
                        corrected_source=linking.product_leg,
                    )
                )
        if accrued_interest is not None:
            fields_to_clear = (
                frozenset(
                    field_name
                    for field_name in (
                        "external_cash_transaction_id",
                        "linked_component_ids",
                    )
                    if getattr(accrued_interest, field_name) is None
                )
                if prior_interest is not None
                else frozenset()
            )
            await transaction_state.upsert_generated_booked_transaction(
                accrued_interest,
                fields_to_clear=fields_to_clear,
            )
            emitted_transactions.append(
                _with_source_epoch(accrued_interest, source_epoch=source_epoch)
            )
        if linking.generated_cash_leg is not None:
            emitted_transactions.append(
                _with_source_epoch(linking.generated_cash_leg, source_epoch=source_epoch)
            )

    staged_transactions = tuple(emitted_transactions)
    staged_instruments = tuple(instrument_updates)
    await effect_stager.stage_processed_transactions(
        staged_transactions,
        correlation_id=correlation_id,
    )
    await effect_stager.stage_instrument_updates(
        staged_instruments,
        correlation_id=correlation_id,
    )
    return CostProcessingResult(
        processed_transactions=staged_transactions,
        instrument_update_count=len(staged_instruments),
    )


def _with_source_epoch(
    transaction: BookedTransaction,
    *,
    source_epoch: int | None,
) -> BookedTransaction:
    if source_epoch is None:
        return transaction
    return replace(transaction, epoch=source_epoch)
