"""Execute prepared cost-basis and foreign-exchange transaction processing."""

from collections.abc import Sequence
from dataclasses import replace

from portfolio_common.domain.cost_basis_method import CostBasisMethod

from ...domain.cost_basis import (
    CostBasisProcessingCheckpoint,
    CostBasisTransaction,
    CostCalculationError,
    transaction_order_key,
)
from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import FxContractInstrument
from ...domain.transaction.redemption import (
    assert_linked_redemption_interest_unambiguous,
    requires_linked_redemption_interest_history,
)
from ...ports import (
    AccruedIncomeOffsetStatePort,
    CorporateActionReconciliationObserver,
    CorporateActionReconciliationRepository,
    CostBasisAverageCostPoolPort,
    CostBasisCalculationObserver,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotBasisTransferPort,
    CostBasisLotDisposalPort,
    CostBasisLotStatePort,
    CostBasisPersistenceObserver,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
    InitialOpeningCostStatePort,
    LotAmortizedCostProfilePort,
)
from ..errors import TransactionProcessingRejected
from ..foreign_exchange_processing import book_foreign_exchange_transaction
from .amortized_disposal import apply_effective_amortized_cost_to_disposals
from .basis_transfer_persistence import persist_current_lot_basis_transfers
from .calculation import CostBasisCalculationCoordinator
from .disposal_persistence import persist_current_lot_disposals
from .effect_coordination import coordinate_cost_processing_effects
from .lot_state_persistence import OpenLotPersistenceScope, persist_open_lot_state
from .persistence_scope import CostBasisTransactionPersistenceScope
from .preparation import CostProcessingRoute, PreparedCostTransaction
from .transaction_persistence import persist_cost_basis_transactions

# Correction commands replay the earliest affected booked transaction; its full cost-basis rebuild
# recalculates the complete suffix before one unit-of-work commit.
_AMORTIZED_DISPOSAL_RUNTIME_ENABLED = True


class PreparedCostProcessingUseCase:
    """Persist one prepared transaction and stage all resulting domain effects."""

    def __init__(
        self,
        *,
        calculation_observer: CostBasisCalculationObserver | None = None,
        persistence_observer: CostBasisPersistenceObserver | None = None,
        reconciliation_observer: CorporateActionReconciliationObserver | None = None,
    ) -> None:
        self._calculation_observer = calculation_observer
        self._persistence_observer = persistence_observer
        self._reconciliation_observer = reconciliation_observer

    async def execute(
        self,
        *,
        prepared: PreparedCostTransaction,
        portfolio: CostBasisPortfolioReference,
        instrument: CostBasisInstrumentReference | None,
        transaction_state: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_disposals: CostBasisLotDisposalPort,
        lot_basis_transfers: CostBasisLotBasisTransferPort,
        lot_states: CostBasisLotStatePort,
        amortized_cost_profiles: LotAmortizedCostProfilePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        initial_opening_state: InitialOpeningCostStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        effect_stager: CostProcessingEffectStagingPort,
        correlation_id: str,
        reconcile_superseded_derived: bool = False,
    ) -> CostProcessingResult:
        """Execute the selected route and coordinate its settlement and delivery effects."""

        if prepared.route is CostProcessingRoute.FOREIGN_EXCHANGE:
            processed_transactions, instrument_updates = await self._book_foreign_exchange(
                prepared=prepared,
                transaction_state=transaction_state,
            )
        else:
            processed_transactions = await self._calculate_cost_basis(
                prepared=prepared,
                portfolio=portfolio,
                instrument=instrument,
                transaction_state=transaction_state,
                average_cost_pools=average_cost_pools,
                lot_disposals=lot_disposals,
                lot_basis_transfers=lot_basis_transfers,
                lot_states=lot_states,
                amortized_cost_profiles=amortized_cost_profiles,
                income_offsets=income_offsets,
                initial_opening_state=initial_opening_state,
                fx_rates=fx_rates,
                processing_state=processing_state,
            )
            instrument_updates = ()

        processed_transactions = tuple(
            replace(transaction, tenant_id=prepared.transaction.tenant_id)
            for transaction in processed_transactions
        )
        return await coordinate_cost_processing_effects(
            processed_transactions=processed_transactions,
            instrument_updates=instrument_updates,
            source_epoch=prepared.transaction.epoch,
            transaction_state=transaction_state,
            reconciliation_repository=reconciliation_repository,
            effect_stager=effect_stager,
            correlation_id=correlation_id,
            corrected_transaction_id=(
                prepared.transaction.transaction_id if reconcile_superseded_derived else None
            ),
            reconciliation_observer=self._reconciliation_observer,
        )

    @staticmethod
    async def _book_foreign_exchange(
        *,
        prepared: PreparedCostTransaction,
        transaction_state: CostBasisTransactionStatePort,
    ) -> tuple[tuple[BookedTransaction, ...], tuple[FxContractInstrument, ...]]:
        booking = await book_foreign_exchange_transaction(
            transaction=prepared.transaction,
            transaction_persistence=transaction_state,
        )
        instruments = (
            (booking.contract_instrument,) if booking.contract_instrument is not None else ()
        )
        return (booking.transaction,), instruments

    async def _calculate_cost_basis(
        self,
        *,
        prepared: PreparedCostTransaction,
        portfolio: CostBasisPortfolioReference,
        instrument: CostBasisInstrumentReference | None,
        transaction_state: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_disposals: CostBasisLotDisposalPort,
        lot_basis_transfers: CostBasisLotBasisTransferPort,
        lot_states: CostBasisLotStatePort,
        amortized_cost_profiles: LotAmortizedCostProfilePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        initial_opening_state: InitialOpeningCostStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
    ) -> tuple[BookedTransaction, ...]:
        transaction = prepared.transaction
        await processing_state.acquire_cost_basis_processing_lock(
            transaction.portfolio_id,
            transaction.security_id,
        )
        # Lock order is invariant: portfolio/security first, then portfolio/linked-group.
        # No path may acquire these in reverse order or acquire a second security lock.
        if requires_linked_redemption_interest_history(transaction):
            await processing_state.acquire_linked_redemption_group_lock(
                transaction.portfolio_id,
                transaction.linked_transaction_group_id or "",
            )
        await _validate_linked_redemption_group(
            transaction=transaction,
            transaction_state=transaction_state,
        )
        calculation = await CostBasisCalculationCoordinator(
            transactions=transaction_state,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            fx_rates=fx_rates,
            processing_state=processing_state,
            observer=self._calculation_observer,
        ).calculate(
            transaction=transaction,
            transaction_type=prepared.transaction_type,
            portfolio_base_currency=portfolio.base_currency,
            instrument=instrument,
            cost_basis_method=prepared.cost_basis_method,
        )
        _raise_for_calculation_errors(calculation.errored)
        if _AMORTIZED_DISPOSAL_RUNTIME_ENABLED:
            calculation = await apply_effective_amortized_cost_to_disposals(
                calculation,
                portfolio=portfolio,
                cost_basis_method=prepared.cost_basis_method,
                profiles=amortized_cost_profiles,
            )
        initial_opening_checkpoint = (
            _processing_checkpoint(
                processed=calculation.processed,
                cost_basis_method=prepared.cost_basis_method,
            )
            if (
                prepared.transaction_type == "BUY"
                and calculation.open_lot_persistence_scope
                is OpenLotPersistenceScope.INITIAL_OPENING_LOT
            )
            else None
        )
        persisted_transactions = await persist_cost_basis_transactions(
            processed=calculation.processed,
            incoming_transaction_ids={transaction.transaction_id},
            transactions=transaction_state,
            lot_states=lot_states,
            income_offsets=income_offsets,
            initial_opening_state=initial_opening_state,
            initial_opening_checkpoint=initial_opening_checkpoint,
            observer=self._persistence_observer,
            persistence_scope=(
                CostBasisTransactionPersistenceScope.AFFECTED_SUFFIX
                if calculation.incremental
                else CostBasisTransactionPersistenceScope.REBUILD_AUTHORITY
            ),
            missing_authority_transaction_ids=(
                calculation.missing_economics_authority_transaction_ids
            ),
        )
        await persist_current_lot_disposals(
            processed=calculation.processed,
            incoming_transaction_ids={transaction.transaction_id},
            disposals=calculation.disposals,
            cost_basis_method=prepared.cost_basis_method,
            repository=lot_disposals,
        )
        await persist_current_lot_basis_transfers(
            processed=calculation.processed,
            incoming_transaction_ids={transaction.transaction_id},
            basis_transfers=calculation.basis_transfers,
            cost_basis_method=prepared.cost_basis_method,
            repository=lot_basis_transfers,
        )
        await persist_open_lot_state(
            transaction=transaction,
            effective_transaction_type=prepared.transaction_type,
            open_lot_states=calculation.open_lot_states,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            incremental=calculation.incremental,
            persistence_scope=calculation.open_lot_persistence_scope,
            cost_basis_method=prepared.cost_basis_method,
            average_cost_pool_transition=calculation.average_cost_pool_transition,
            processed=calculation.processed,
        )
        if initial_opening_checkpoint is None:
            await _persist_processing_checkpoint(
                processed=calculation.processed,
                cost_basis_method=prepared.cost_basis_method,
                processing_state=processing_state,
            )
        return tuple(persisted_transactions)


async def _validate_linked_redemption_group(
    *,
    transaction: BookedTransaction,
    transaction_state: CostBasisTransactionStatePort,
) -> None:
    """Validate one portfolio-owned linked group before cost or lot mutation."""

    if not requires_linked_redemption_interest_history(transaction):
        return
    history = await transaction_state.get_linked_transaction_group(
        portfolio_id=transaction.portfolio_id,
        linked_transaction_group_id=transaction.linked_transaction_group_id or "",
        exclude_id=transaction.transaction_id,
    )
    assert_linked_redemption_interest_unambiguous(
        incoming=transaction,
        history=history,
    )


async def _persist_processing_checkpoint(
    *,
    processed: Sequence[CostBasisTransaction],
    cost_basis_method: CostBasisMethod,
    processing_state: CostBasisProcessingStatePort,
) -> None:
    await processing_state.upsert_cost_basis_processing_checkpoint(
        _processing_checkpoint(processed=processed, cost_basis_method=cost_basis_method)
    )


def _processing_checkpoint(
    *,
    processed: Sequence[CostBasisTransaction],
    cost_basis_method: CostBasisMethod,
) -> CostBasisProcessingCheckpoint:
    latest_transaction = max(processed, key=transaction_order_key)
    return CostBasisProcessingCheckpoint.from_transaction(
        latest_transaction,
        cost_basis_method=cost_basis_method,
    )


def _raise_for_calculation_errors(errors: Sequence[CostCalculationError]) -> None:
    if not errors:
        return
    first_error = errors[0]
    if first_error.error_reason.startswith("Quantity restatement invariant violation:"):
        raise TransactionProcessingRejected(
            reason_code="lot_quantity_restatement_rejected",
            detail={
                "transaction_id": first_error.transaction_id,
                "reason": "lot_restatement_invariant_violation",
            },
            retryable=False,
        )
    raise ValueError(
        f"Cost-basis calculation failed for {first_error.transaction_id}: "
        f"{first_error.error_reason}"
    )
