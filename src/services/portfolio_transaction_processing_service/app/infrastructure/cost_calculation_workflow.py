"""Stage cost-basis effects inside the unified transaction-processing boundary."""

from typing import Any

from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import TransactionEvent

from ..application import CorporateActionReconciliationCoordinator
from ..application.cost_basis_processing import (
    CostBasisCalculationCoordinator,
    CostProcessingRoute,
    persist_cost_basis_transactions,
    persist_open_lot_state,
)
from ..application.foreign_exchange_processing import book_foreign_exchange_transaction
from ..application.settlement_processing import link_settlement_cash_leg
from ..domain.cost_basis import (
    CostBasisProcessingCheckpoint,
    transaction_order_key,
)
from ..domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from ..domain.transaction.fx import FxContractInstrument
from ..ports import (
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
)
from .booked_transaction_event_mapper import (
    to_booked_transaction,
    to_transaction_event,
    with_booked_transaction_fields,
)
from .cost_basis.staged_effects import StagedCostEffects


class CostCalculationWorkflow:
    """
    Calculates and stages cost, lot, transaction, instrument, and outbox effects.

    Database transaction, idempotency, retry, and delivery lifecycle ownership remain outside this
    workflow.
    """

    _cost_basis_observer: CostBasisCalculationObserver | None = None
    _cost_basis_persistence_observer: CostBasisPersistenceObserver | None = None
    _corporate_action_reconciliation_observer: CorporateActionReconciliationObserver | None = None

    def configure_cost_basis_observer(self, observer: CostBasisCalculationObserver) -> None:
        """Attach infrastructure observability without changing legacy delivery construction."""
        self._cost_basis_observer = observer

    def configure_cost_basis_persistence_observer(
        self,
        observer: CostBasisPersistenceObserver,
    ) -> None:
        """Attach infrastructure persistence telemetry to the application use case."""

        self._cost_basis_persistence_observer = observer

    def configure_corporate_action_reconciliation_observer(
        self,
        observer: CorporateActionReconciliationObserver,
    ) -> None:
        """Attach corporate-action support telemetry at the infrastructure boundary."""

        self._corporate_action_reconciliation_observer = observer

    async def _build_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        route: CostProcessingRoute,
        portfolio: CostBasisPortfolioReference,
        instrument: CostBasisInstrumentReference | None,
        repo: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_states: CostBasisLotStatePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        cost_basis_method: CostBasisMethod,
    ) -> tuple[list[TransactionEvent], list[FxContractInstrument]]:
        if route is CostProcessingRoute.FOREIGN_EXCHANGE:
            return await self._build_fx_events_to_publish(event=event, repo=repo)
        return await self._build_cost_basis_events_to_publish(
            event=event,
            event_transaction_type=event_transaction_type,
            portfolio=portfolio,
            instrument=instrument,
            repo=repo,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            income_offsets=income_offsets,
            fx_rates=fx_rates,
            processing_state=processing_state,
            cost_basis_method=cost_basis_method,
        )

    async def stage_prepared_event(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        route: CostProcessingRoute,
        portfolio: CostBasisPortfolioReference,
        instrument: CostBasisInstrumentReference | None,
        repo: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_states: CostBasisLotStatePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        cost_basis_method: CostBasisMethod,
        effect_stager: CostProcessingEffectStagingPort,
        correlation_id: str,
    ) -> StagedCostEffects:
        """Stage all cost-derived events through one public infrastructure operation."""

        events_to_publish, instrument_events = await self._build_events_to_publish(
            event=event,
            event_transaction_type=event_transaction_type,
            route=route,
            portfolio=portfolio,
            instrument=instrument,
            repo=repo,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            income_offsets=income_offsets,
            fx_rates=fx_rates,
            processing_state=processing_state,
            cost_basis_method=cost_basis_method,
        )
        emitted_transactions = await self._build_emitted_transaction_events(
            events_to_publish=events_to_publish,
            repo=repo,
            reconciliation_repository=reconciliation_repository,
            correlation_id=correlation_id,
        )
        if event.epoch is not None:
            for emitted_transaction in emitted_transactions:
                emitted_transaction.epoch = event.epoch
        await effect_stager.stage_processed_transactions(
            tuple(to_booked_transaction(item) for item in emitted_transactions),
            correlation_id=correlation_id,
        )
        await effect_stager.stage_instrument_updates(
            tuple(instrument_events),
            correlation_id=correlation_id,
        )
        return StagedCostEffects(
            emitted_transactions=tuple(emitted_transactions),
            instrument_update_count=len(instrument_events),
        )

    async def _build_fx_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        repo: CostBasisTransactionStatePort,
    ) -> tuple[list[TransactionEvent], list[FxContractInstrument]]:
        booking = await book_foreign_exchange_transaction(
            transaction=to_booked_transaction(event),
            transaction_persistence=repo,
        )
        processed_event = with_booked_transaction_fields(event, booking.transaction)
        instruments = (
            [booking.contract_instrument] if booking.contract_instrument is not None else []
        )
        return [processed_event], instruments

    async def _build_cost_basis_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        portfolio: CostBasisPortfolioReference,
        instrument: CostBasisInstrumentReference | None,
        repo: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_states: CostBasisLotStatePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        cost_basis_method: CostBasisMethod,
    ) -> tuple[list[TransactionEvent], list[FxContractInstrument]]:
        await processing_state.acquire_cost_basis_processing_lock(
            event.portfolio_id,
            event.security_id,
        )
        calculation = await CostBasisCalculationCoordinator(
            transactions=repo,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            fx_rates=fx_rates,
            processing_state=processing_state,
            observer=self._cost_basis_observer,
        ).calculate(
            transaction=to_booked_transaction(event),
            transaction_type=event_transaction_type,
            portfolio_base_currency=portfolio.base_currency,
            instrument=instrument,
            cost_basis_method=cost_basis_method,
        )

        new_transaction_ids = {event.transaction_id}
        self._raise_for_transaction_engine_errors(errored=calculation.errored)
        persisted_transactions = await persist_cost_basis_transactions(
            processed=calculation.processed,
            incoming_transaction_ids=new_transaction_ids,
            transactions=repo,
            lot_states=lot_states,
            income_offsets=income_offsets,
            observer=self._cost_basis_persistence_observer,
        )
        events_to_publish = [
            to_transaction_event(
                transaction,
                correlation_id=None,
                traceparent=None,
            )
            for transaction in persisted_transactions
        ]
        await persist_open_lot_state(
            transaction=to_booked_transaction(event),
            effective_transaction_type=event_transaction_type,
            open_lot_states=calculation.open_lot_states,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            incremental=calculation.incremental,
            persistence_scope=calculation.open_lot_persistence_scope,
            cost_basis_method=cost_basis_method,
            average_cost_pool_transition=calculation.average_cost_pool_transition,
        )
        await self._persist_cost_basis_processing_checkpoint(
            processed=calculation.processed,
            cost_basis_method=cost_basis_method,
            processing_state=processing_state,
        )

        return events_to_publish, []

    @staticmethod
    async def _persist_cost_basis_processing_checkpoint(
        *,
        processed: list[EngineTransaction],
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

    @staticmethod
    def _raise_for_transaction_engine_errors(
        *,
        errored: list[Any],
    ) -> None:
        if errored:
            raise ValueError(
                f"Cost-basis calculation failed for {errored[0].transaction_id}: "
                f"{errored[0].error_reason}"
            )

    async def _build_emitted_transaction_events(
        self,
        *,
        events_to_publish: list[TransactionEvent],
        repo: CostBasisTransactionStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        correlation_id: str,
    ) -> list[TransactionEvent]:
        emitted_events: list[TransactionEvent] = []
        corporate_action_reconciliation = CorporateActionReconciliationCoordinator(
            reconciliation_repository,
            observer=self._corporate_action_reconciliation_observer,
        )
        for processed_event in events_to_publish:
            booked_transaction = to_booked_transaction(processed_event)
            linking_result = await link_settlement_cash_leg(
                product_leg=booked_transaction,
                transaction_lookup=repo,
                transaction_persistence=repo,
            )
            processed_event = with_booked_transaction_fields(
                processed_event,
                linking_result.product_leg,
            )
            emitted_events.append(processed_event)
            if linking_result.generated_cash_leg is not None:
                emitted_events.append(
                    to_transaction_event(
                        linking_result.generated_cash_leg,
                        correlation_id=None,
                        traceparent=None,
                    )
                )

            await corporate_action_reconciliation.reconcile(
                to_booked_transaction(processed_event),
                correlation_id=correlation_id,
            )
        return emitted_events
