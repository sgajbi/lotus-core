"""Coordinate settlement, reconciliation, and staging for processed cost effects."""

from collections.abc import Sequence
from dataclasses import replace

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import FxContractInstrument
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
    processed_transactions: Sequence[BookedTransaction],
    instrument_updates: Sequence[FxContractInstrument],
    source_epoch: int | None,
    transaction_state: CostBasisTransactionStatePort,
    reconciliation_repository: CorporateActionReconciliationRepository,
    effect_stager: CostProcessingEffectStagingPort,
    correlation_id: str,
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
        )
        await reconciliation.reconcile(
            linking.product_leg,
            correlation_id=correlation_id,
        )
        emitted_transactions.append(
            _with_source_epoch(linking.product_leg, source_epoch=source_epoch)
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
