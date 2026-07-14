"""Execute prepared cost-basis and foreign-exchange transaction processing."""

from collections.abc import Sequence

from portfolio_common.domain.cost_basis_method import CostBasisMethod

from ...domain.cost_basis import (
    CostBasisProcessingCheckpoint,
    CostBasisTransaction,
    CostCalculationError,
    transaction_order_key,
)
from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import FxContractInstrument
from ...ports import (
    AccruedIncomeOffsetStatePort,
    CorporateActionReconciliationObserver,
    CorporateActionReconciliationRepository,
    CostBasisAverageCostPoolPort,
    CostBasisCalculationObserver,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotStatePort,
    CostBasisPersistenceObserver,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
)
from ..foreign_exchange_processing import book_foreign_exchange_transaction
from .calculation import CostBasisCalculationCoordinator
from .effect_coordination import coordinate_cost_processing_effects
from .lot_state_persistence import persist_open_lot_state
from .preparation import CostProcessingRoute, PreparedCostTransaction
from .transaction_persistence import persist_cost_basis_transactions


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
        lot_states: CostBasisLotStatePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        effect_stager: CostProcessingEffectStagingPort,
        correlation_id: str,
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
                lot_states=lot_states,
                income_offsets=income_offsets,
                fx_rates=fx_rates,
                processing_state=processing_state,
            )
            instrument_updates = ()

        return await coordinate_cost_processing_effects(
            processed_transactions=processed_transactions,
            instrument_updates=instrument_updates,
            source_epoch=prepared.transaction.epoch,
            transaction_state=transaction_state,
            reconciliation_repository=reconciliation_repository,
            effect_stager=effect_stager,
            correlation_id=correlation_id,
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
        lot_states: CostBasisLotStatePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
    ) -> tuple[BookedTransaction, ...]:
        transaction = prepared.transaction
        await processing_state.acquire_cost_basis_processing_lock(
            transaction.portfolio_id,
            transaction.security_id,
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
        persisted_transactions = await persist_cost_basis_transactions(
            processed=calculation.processed,
            incoming_transaction_ids={transaction.transaction_id},
            transactions=transaction_state,
            lot_states=lot_states,
            income_offsets=income_offsets,
            observer=self._persistence_observer,
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
        )
        await _persist_processing_checkpoint(
            processed=calculation.processed,
            cost_basis_method=prepared.cost_basis_method,
            processing_state=processing_state,
        )
        return tuple(persisted_transactions)


async def _persist_processing_checkpoint(
    *,
    processed: Sequence[CostBasisTransaction],
    cost_basis_method: CostBasisMethod,
    processing_state: CostBasisProcessingStatePort,
) -> None:
    latest_transaction = max(processed, key=transaction_order_key)
    await processing_state.upsert_cost_basis_processing_checkpoint(
        CostBasisProcessingCheckpoint.from_transaction(
            latest_transaction,
            cost_basis_method=cost_basis_method,
        )
    )


def _raise_for_calculation_errors(errors: Sequence[CostCalculationError]) -> None:
    if errors:
        raise ValueError(
            f"Cost-basis calculation failed for {errors[0].transaction_id}: "
            f"{errors[0].error_reason}"
        )
