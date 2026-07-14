"""Stage cost-basis effects inside the unified transaction-processing boundary."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

from portfolio_common.config import (
    KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
    KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import InstrumentEvent, TransactionEvent, event_business_payload
from portfolio_common.monitoring import BUY_LIFECYCLE_STAGE_TOTAL, SELL_LIFECYCLE_STAGE_TOTAL
from portfolio_common.outbox_repository import OutboxRepository

from ..application import (
    CorporateActionReconciliationCoordinator,
    CostBasisTimelineProcessor,
    build_cost_basis_timeline_processor,
)
from ..application.cost_basis_processing import (
    CostBasisCalculationResult,
    CostProcessingRoute,
    OpenLotPersistenceScope,
    enrich_cost_basis_transactions_with_fx,
    persist_cost_basis_transactions,
    persist_open_lot_state,
)
from ..application.settlement_processing import validate_upstream_cash_leg
from ..domain.cost_basis import (
    AVERAGE_COST_POOL_LOT_BEHAVIORS,
    INCREMENTAL_SAFE_LOT_BEHAVIORS,
    STATE_DEPENDENT_LOT_BEHAVIORS,
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    CostBasisProcessingCheckpoint,
    OpenLotState,
    build_cost_basis_engine_input,
    transaction_lot_behavior,
    transaction_order_key,
)
from ..domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from ..domain.transaction import (
    build_generated_settlement_cash_leg,
    should_generate_settlement_cash_leg,
)
from ..domain.transaction.fx import (
    assert_fx_processed_transaction_valid,
    build_fx_contract_instrument,
    build_fx_processed_transaction,
)
from ..ports import (
    AccruedIncomeOffsetStatePort,
    AverageCostPoolCheckpointRecord,
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
)
from .booked_transaction_event_mapper import (
    to_booked_transaction,
    to_transaction_event,
    with_booked_transaction_fields,
)
from .cost_basis.metrics import COST_PROCESSING_EXECUTION_TOTAL, COST_PROCESSING_OPEN_LOTS_RESTORED
from .cost_basis.staged_effects import StagedCostEffects
from .fx_event_mapper import to_fx_contract_instrument_event


def _normalize_event_code(value: object) -> str:
    return str(value or "").strip().upper()


def _record_outbox_lifecycle(transaction_type: object) -> None:
    """Preserve BUY/SELL outbox lifecycle metrics at the infrastructure boundary."""

    counter = {
        "BUY": BUY_LIFECYCLE_STAGE_TOTAL,
        "SELL": SELL_LIFECYCLE_STAGE_TOTAL,
    }.get(_normalize_event_code(transaction_type))
    if counter is not None:
        counter.labels("emit_outbox", "success").inc()


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

    def _get_cost_basis_timeline_processor(
        self, cost_basis_method: str | CostBasisMethod = CostBasisMethod.FIFO
    ) -> CostBasisTimelineProcessor:
        return build_cost_basis_timeline_processor(
            cost_basis_method,
            observer=self._cost_basis_observer,
        )

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
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]:
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
        outbox_repo: OutboxRepository,
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
        await self._publish_transaction_events(
            original_event=event,
            emitted_events=emitted_transactions,
            outbox_repo=outbox_repo,
            correlation_id=correlation_id,
        )
        await self._publish_instrument_events(
            instrument_events=instrument_events,
            outbox_repo=outbox_repo,
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
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]:
        processed_transaction = build_fx_processed_transaction(to_booked_transaction(event))
        assert_fx_processed_transaction_valid(processed_transaction)
        processed_event = with_booked_transaction_fields(event, processed_transaction)
        await repo.upsert_booked_transaction(processed_transaction)
        instrument_events = []
        contract_instrument = build_fx_contract_instrument(processed_transaction)
        if contract_instrument is not None:
            instrument_events.append(to_fx_contract_instrument_event(contract_instrument))
        return [processed_event], instrument_events

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
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]:
        await processing_state.acquire_cost_basis_processing_lock(
            event.portfolio_id,
            event.security_id,
        )
        calculation = await self._calculate_cost_basis(
            event=event,
            event_transaction_type=event_transaction_type,
            portfolio_base_currency=portfolio.base_currency,
            instrument=instrument,
            repo=repo,
            average_cost_pools=average_cost_pools,
            lot_states=lot_states,
            fx_rates=fx_rates,
            processing_state=processing_state,
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

    async def _calculate_cost_basis(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        repo: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_states: CostBasisLotStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        cost_basis_method: CostBasisMethod,
    ) -> CostBasisCalculationResult:
        checkpoint = await processing_state.get_cost_basis_processing_checkpoint(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
        )
        lot_behavior = transaction_lot_behavior(event_transaction_type)
        if checkpoint is not None and lot_behavior in INCREMENTAL_SAFE_LOT_BEHAVIORS:
            incoming_raw = await self._load_incoming_cost_basis_transaction(
                event=event,
                portfolio_base_currency=portfolio_base_currency,
                instrument=instrument,
                repo=repo,
                fx_rates=fx_rates,
            )
            incoming_transaction = EngineTransaction(**incoming_raw)
            if checkpoint.permits_append(
                incoming_transaction,
                cost_basis_method=cost_basis_method,
            ):
                average_cost_pool_record = None
                if (
                    cost_basis_method is CostBasisMethod.AVCO
                    and lot_behavior in AVERAGE_COST_POOL_LOT_BEHAVIORS
                ):
                    average_cost_pool_record = (
                        await self._get_compatible_average_cost_pool_checkpoint(
                            event=event,
                            average_cost_pools=average_cost_pools,
                        )
                    )
                    if average_cost_pool_record is None:
                        return await self._calculate_full_cost_rebuild(
                            event=event,
                            portfolio_base_currency=portfolio_base_currency,
                            instrument=instrument,
                            repo=repo,
                            fx_rates=fx_rates,
                            cost_basis_method=cost_basis_method,
                        )
                initial_open_lots_raw = []
                open_lot_persistence_scope = OpenLotPersistenceScope.COMPLETE_SNAPSHOT
                if average_cost_pool_record is not None:
                    initial_open_lots_raw = self._load_average_cost_pool_checkpoint_transaction(
                        record=average_cost_pool_record,
                        portfolio_base_currency=portfolio_base_currency,
                        instrument=instrument,
                    )
                    open_lot_persistence_scope = OpenLotPersistenceScope.AVERAGE_COST_POOL
                elif lot_behavior in STATE_DEPENDENT_LOT_BEHAVIORS:
                    required_fifo_quantity = (
                        incoming_transaction.quantity
                        if cost_basis_method is CostBasisMethod.FIFO
                        and lot_behavior == "consume_lot"
                        and incoming_transaction.quantity > Decimal(0)
                        else None
                    )
                    initial_open_lots_raw = await self._load_open_lot_checkpoint_transactions(
                        event=event,
                        portfolio_base_currency=portfolio_base_currency,
                        instrument=instrument,
                        lot_states=lot_states,
                        required_fifo_quantity=required_fifo_quantity,
                    )
                    if required_fifo_quantity is not None:
                        open_lot_persistence_scope = OpenLotPersistenceScope.SELECTED_LOTS
                if (
                    average_cost_pool_record is not None
                    or lot_behavior in STATE_DEPENDENT_LOT_BEHAVIORS
                ):
                    COST_PROCESSING_OPEN_LOTS_RESTORED.labels(
                        cost_basis_method=cost_basis_method.value
                    ).observe(len(initial_open_lots_raw))
                processed, errored, open_lot_states = self._get_cost_basis_timeline_processor(
                    cost_basis_method
                ).process_increment(
                    initial_open_lots_raw=initial_open_lots_raw,
                    new_transactions_raw=[incoming_raw],
                )
                average_cost_pool_transition = (
                    self._build_average_cost_pool_transition(
                        checkpoint=average_cost_pool_record.checkpoint,
                        open_lot_states=open_lot_states,
                    )
                    if average_cost_pool_record is not None and not errored
                    else None
                )
                COST_PROCESSING_EXECUTION_TOTAL.labels(
                    mode="ordered_append",
                    cost_basis_method=cost_basis_method.value,
                ).inc()
                return CostBasisCalculationResult(
                    processed=processed,
                    errored=errored,
                    open_lot_states=open_lot_states,
                    incremental=True,
                    open_lot_persistence_scope=open_lot_persistence_scope,
                    average_cost_pool_transition=average_cost_pool_transition,
                )

        return await self._calculate_full_cost_rebuild(
            event=event,
            portfolio_base_currency=portfolio_base_currency,
            instrument=instrument,
            repo=repo,
            fx_rates=fx_rates,
            cost_basis_method=cost_basis_method,
        )

    async def _calculate_full_cost_rebuild(
        self,
        *,
        event: TransactionEvent,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        repo: CostBasisTransactionStatePort,
        fx_rates: CostBasisFxRatePort,
        cost_basis_method: CostBasisMethod,
    ) -> CostBasisCalculationResult:
        all_transactions_raw = await self._load_cost_basis_transactions(
            event=event,
            portfolio_base_currency=portfolio_base_currency,
            instrument=instrument,
            repo=repo,
            fx_rates=fx_rates,
        )
        processed, errored, open_lot_states = self._get_cost_basis_timeline_processor(
            cost_basis_method
        ).process_transactions(
            existing_transactions_raw=[],
            new_transactions_raw=all_transactions_raw,
        )
        COST_PROCESSING_EXECUTION_TOTAL.labels(
            mode="full_rebuild",
            cost_basis_method=cost_basis_method.value,
        ).inc()
        return CostBasisCalculationResult(
            processed=processed,
            errored=errored,
            open_lot_states=open_lot_states,
            incremental=False,
            open_lot_persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
            average_cost_pool_transition=None,
        )

    async def _load_incoming_cost_basis_transaction(
        self,
        *,
        event: TransactionEvent,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        repo: CostBasisTransactionStatePort,
        fx_rates: CostBasisFxRatePort,
    ) -> dict[str, Any]:
        event_raw = build_cost_basis_engine_input(to_booked_transaction(event))
        if instrument is not None:
            self._attach_instrument_metadata(transactions=[event_raw], instrument=instrument)
        enriched: list[dict[str, Any]] = await enrich_cost_basis_transactions_with_fx(
            transactions=[event_raw],
            portfolio_base_currency=portfolio_base_currency,
            fx_rates=fx_rates,
        )
        return enriched[0]

    @staticmethod
    async def _get_compatible_average_cost_pool_checkpoint(
        *,
        event: TransactionEvent,
        average_cost_pools: CostBasisAverageCostPoolPort,
    ) -> AverageCostPoolCheckpointRecord | None:
        record = await average_cost_pools.get_average_cost_pool_checkpoint_record(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
        )
        if record is None or not record.checkpoint.is_compatible(
            portfolio_id=event.portfolio_id,
            instrument_id=event.instrument_id,
            security_id=event.security_id,
        ):
            return None
        if record.checkpoint.quantity > Decimal(0) and record.representative_transaction is None:
            return None
        return record

    def _load_average_cost_pool_checkpoint_transaction(
        self,
        *,
        record: AverageCostPoolCheckpointRecord,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
    ) -> list[dict[str, Any]]:
        checkpoint = record.checkpoint
        if checkpoint.quantity == Decimal(0):
            return []
        if record.representative_transaction is None:
            raise ValueError("Open average cost pool has no representative transaction")
        transaction_raw = build_cost_basis_engine_input(record.representative_transaction)
        transaction_raw["source_lot_order_quantity"] = transaction_raw["quantity"]
        transaction_raw["quantity"] = checkpoint.quantity
        transaction_raw["net_cost_local"] = checkpoint.cost_local
        transaction_raw["net_cost"] = checkpoint.cost_base
        transaction_raw["portfolio_base_currency"] = portfolio_base_currency
        if instrument is not None:
            self._attach_instrument_metadata(
                transactions=[transaction_raw],
                instrument=instrument,
            )
        return [transaction_raw]

    @staticmethod
    def _build_average_cost_pool_transition(
        *,
        checkpoint: AverageCostPoolCheckpoint,
        open_lot_states: dict[str, OpenLotState],
    ) -> AverageCostPoolTransition:
        remaining_states = dict(open_lot_states)
        if checkpoint.quantity > Decimal(0):
            representative_source_id = checkpoint.representative_source_transaction_id
            if representative_source_id is None:
                raise ValueError("Open average cost pool has no representative source")
            existing_sources_after = remaining_states.pop(
                representative_source_id,
                None,
            )
            if existing_sources_after is None:
                raise ValueError(
                    "Average cost calculation omitted the aggregate representative source"
                )
        else:
            existing_sources_after = OpenLotState(
                quantity=Decimal(0),
                cost_local=Decimal(0),
                cost_base=Decimal(0),
            )
        return AverageCostPoolTransition(
            before=checkpoint,
            existing_sources_after=existing_sources_after,
            explicit_sources_after=remaining_states,
        )

    async def _load_open_lot_checkpoint_transactions(
        self,
        *,
        event: TransactionEvent,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        lot_states: CostBasisLotStatePort,
        required_fifo_quantity: Decimal | None = None,
    ) -> list[dict[str, Any]]:
        if required_fifo_quantity is None:
            records = await lot_states.get_open_lot_checkpoint_records(
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
            )
        else:
            records = await lot_states.get_fifo_disposal_lot_checkpoint_records(
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
                required_quantity=required_fifo_quantity,
            )
        checkpoint_transactions: list[dict[str, Any]] = []
        for record in records:
            transaction_raw = build_cost_basis_engine_input(record.transaction)
            transaction_raw["source_lot_order_quantity"] = transaction_raw["quantity"]
            transaction_raw["quantity"] = record.quantity
            transaction_raw["net_cost_local"] = record.cost_local
            transaction_raw["net_cost"] = record.cost_base
            transaction_raw["portfolio_base_currency"] = portfolio_base_currency
            checkpoint_transactions.append(transaction_raw)
        if instrument is not None:
            self._attach_instrument_metadata(
                transactions=checkpoint_transactions,
                instrument=instrument,
            )
        return checkpoint_transactions

    async def _load_cost_basis_transactions(
        self,
        *,
        event: TransactionEvent,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        repo: CostBasisTransactionStatePort,
        fx_rates: CostBasisFxRatePort,
    ) -> list[dict[str, Any]]:
        history = await repo.get_transaction_history(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            exclude_id=event.transaction_id,
        )
        history_raw = [build_cost_basis_engine_input(transaction) for transaction in history]
        event_raw = build_cost_basis_engine_input(to_booked_transaction(event))
        all_transactions_raw = [*history_raw, event_raw]
        if instrument is not None:
            self._attach_instrument_metadata(
                transactions=all_transactions_raw,
                instrument=instrument,
            )
        enriched_transactions: list[dict[str, Any]] = await enrich_cost_basis_transactions_with_fx(
            transactions=all_transactions_raw,
            portfolio_base_currency=portfolio_base_currency,
            fx_rates=fx_rates,
        )
        return enriched_transactions

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
    def _attach_instrument_metadata(
        *,
        transactions: list[dict[str, Any]],
        instrument: CostBasisInstrumentReference,
    ) -> None:
        for txn_raw in transactions:
            txn_raw["product_type"] = instrument.product_type
            txn_raw["asset_class"] = instrument.asset_class

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
            await validate_upstream_cash_leg(product_leg=booked_transaction, transactions=repo)
            generated_cash_leg = None
            if should_generate_settlement_cash_leg(booked_transaction):
                generated_cash_transaction = build_generated_settlement_cash_leg(booked_transaction)
                generated_cash_leg = to_transaction_event(
                    generated_cash_transaction,
                    correlation_id=None,
                    traceparent=None,
                )
                await repo.upsert_booked_transaction(generated_cash_transaction)
                linked_product_transaction = replace(
                    booked_transaction,
                    external_cash_transaction_id=generated_cash_transaction.transaction_id,
                )
                processed_event = with_booked_transaction_fields(
                    processed_event,
                    linked_product_transaction,
                )
                await repo.upsert_booked_transaction(linked_product_transaction)
            emitted_events.append(processed_event)
            if generated_cash_leg is not None:
                emitted_events.append(generated_cash_leg)

            await corporate_action_reconciliation.reconcile(
                to_booked_transaction(processed_event),
                correlation_id=correlation_id,
            )
        return emitted_events

    async def _publish_transaction_events(
        self,
        *,
        original_event: TransactionEvent,
        emitted_events: list[TransactionEvent],
        outbox_repo: OutboxRepository,
        correlation_id: str,
    ) -> None:
        for publish_event in emitted_events:
            if original_event.epoch is not None:
                publish_event.epoch = original_event.epoch

            await outbox_repo.create_outbox_event(
                aggregate_type="ProcessedTransaction",
                aggregate_id=str(publish_event.portfolio_id),
                event_type="ProcessedTransactionPersisted",
                topic=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
                payload=event_business_payload(publish_event, mode="json"),
                correlation_id=correlation_id,
            )
            _record_outbox_lifecycle(publish_event.transaction_type)

    async def _publish_instrument_events(
        self,
        *,
        instrument_events: list[InstrumentEvent],
        outbox_repo: OutboxRepository,
        correlation_id: str,
    ) -> None:
        for instrument_event in instrument_events:
            await outbox_repo.create_outbox_event(
                aggregate_type="Instrument",
                aggregate_id=str(instrument_event.security_id),
                event_type="InstrumentUpserted",
                topic=KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
                payload=instrument_event.model_dump(mode="json"),
                correlation_id=correlation_id,
            )
