"""Select and execute deterministic incremental or full cost-basis calculation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from portfolio_common.domain.cost_basis_method import CostBasisMethod

from ...domain.cost_basis import (
    AVERAGE_COST_POOL_LOT_BEHAVIORS,
    INCREMENTAL_SAFE_LOT_BEHAVIORS,
    STATE_DEPENDENT_LOT_BEHAVIORS,
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    CostBasisTransaction,
    OpenLotState,
    build_cost_basis_engine_input,
    transaction_lot_behavior,
)
from ...domain.transaction import BookedTransaction
from ...ports.cost_basis import (
    AverageCostPoolCheckpointRecord,
    CostBasisAverageCostPoolPort,
    CostBasisCalculationObserver,
    CostBasisExecutionMode,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotStatePort,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
)
from .calculation_result import CostBasisCalculationResult
from .fx_enrichment import enrich_cost_basis_transactions_with_fx
from .lot_state_persistence import OpenLotPersistenceScope
from .timeline import build_cost_basis_timeline_processor


class CostBasisCalculationCoordinator:
    """Calculate one booked transaction against the appropriate cost-basis timeline."""

    def __init__(
        self,
        *,
        transactions: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_states: CostBasisLotStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        observer: CostBasisCalculationObserver | None = None,
    ) -> None:
        """Bind the framework-neutral state and observation ports used by the calculation."""

        self._transactions = transactions
        self._average_cost_pools = average_cost_pools
        self._lot_states = lot_states
        self._fx_rates = fx_rates
        self._processing_state = processing_state
        self._observer = observer

    async def calculate(
        self,
        *,
        transaction: BookedTransaction,
        transaction_type: str,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        cost_basis_method: CostBasisMethod,
    ) -> CostBasisCalculationResult:
        """Use an ordered append when checkpoints permit it, otherwise rebuild deterministically."""

        checkpoint = await self._processing_state.get_cost_basis_processing_checkpoint(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
        )
        lot_behavior = transaction_lot_behavior(transaction_type)
        if checkpoint is not None and lot_behavior in INCREMENTAL_SAFE_LOT_BEHAVIORS:
            incoming_raw = await self._load_incoming_transaction(
                transaction=transaction,
                portfolio_base_currency=portfolio_base_currency,
                instrument=instrument,
            )
            incoming_transaction = CostBasisTransaction(**incoming_raw)
            if checkpoint.permits_append(
                incoming_transaction,
                cost_basis_method=cost_basis_method,
            ):
                return await self._calculate_ordered_append(
                    transaction=transaction,
                    transaction_type=transaction_type,
                    incoming_raw=incoming_raw,
                    incoming_transaction=incoming_transaction,
                    portfolio_base_currency=portfolio_base_currency,
                    instrument=instrument,
                    cost_basis_method=cost_basis_method,
                )

        return await self._calculate_full_rebuild(
            transaction=transaction,
            portfolio_base_currency=portfolio_base_currency,
            instrument=instrument,
            cost_basis_method=cost_basis_method,
        )

    async def _calculate_ordered_append(
        self,
        *,
        transaction: BookedTransaction,
        transaction_type: str,
        incoming_raw: dict[str, Any],
        incoming_transaction: CostBasisTransaction,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        cost_basis_method: CostBasisMethod,
    ) -> CostBasisCalculationResult:
        lot_behavior = transaction_lot_behavior(transaction_type)
        average_cost_pool_record = None
        if (
            cost_basis_method is CostBasisMethod.AVCO
            and lot_behavior in AVERAGE_COST_POOL_LOT_BEHAVIORS
        ):
            average_cost_pool_record = await self._get_compatible_average_cost_pool_checkpoint(
                transaction
            )
            if average_cost_pool_record is None:
                return await self._calculate_full_rebuild(
                    transaction=transaction,
                    portfolio_base_currency=portfolio_base_currency,
                    instrument=instrument,
                    cost_basis_method=cost_basis_method,
                )

        initial_open_lots_raw: list[dict[str, Any]] = []
        persistence_scope = OpenLotPersistenceScope.COMPLETE_SNAPSHOT
        if average_cost_pool_record is not None:
            initial_open_lots_raw = self._load_average_cost_pool_checkpoint_transaction(
                record=average_cost_pool_record,
                portfolio_base_currency=portfolio_base_currency,
                instrument=instrument,
            )
            persistence_scope = OpenLotPersistenceScope.AVERAGE_COST_POOL
        elif lot_behavior in STATE_DEPENDENT_LOT_BEHAVIORS:
            required_fifo_quantity = (
                incoming_transaction.quantity
                if cost_basis_method is CostBasisMethod.FIFO
                and lot_behavior == "consume_lot"
                and incoming_transaction.quantity > Decimal(0)
                else None
            )
            initial_open_lots_raw = await self._load_open_lot_checkpoint_transactions(
                transaction=transaction,
                portfolio_base_currency=portfolio_base_currency,
                instrument=instrument,
                required_fifo_quantity=required_fifo_quantity,
            )
            if required_fifo_quantity is not None:
                persistence_scope = OpenLotPersistenceScope.SELECTED_LOTS

        if average_cost_pool_record is not None or lot_behavior in STATE_DEPENDENT_LOT_BEHAVIORS:
            self._record_restored_open_lots(
                cost_basis_method=cost_basis_method,
                lot_count=len(initial_open_lots_raw),
            )

        processed, errored, open_lot_states = build_cost_basis_timeline_processor(
            cost_basis_method,
            observer=self._observer,
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
        self._record_execution(CostBasisExecutionMode.ORDERED_APPEND, cost_basis_method)
        return CostBasisCalculationResult(
            processed=processed,
            errored=errored,
            open_lot_states=open_lot_states,
            incremental=True,
            open_lot_persistence_scope=persistence_scope,
            average_cost_pool_transition=average_cost_pool_transition,
        )

    async def _calculate_full_rebuild(
        self,
        *,
        transaction: BookedTransaction,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        cost_basis_method: CostBasisMethod,
    ) -> CostBasisCalculationResult:
        all_transactions_raw = await self._load_cost_basis_transactions(
            transaction=transaction,
            portfolio_base_currency=portfolio_base_currency,
            instrument=instrument,
        )
        processed, errored, open_lot_states = build_cost_basis_timeline_processor(
            cost_basis_method,
            observer=self._observer,
        ).process_transactions(
            existing_transactions_raw=[],
            new_transactions_raw=all_transactions_raw,
        )
        self._record_execution(CostBasisExecutionMode.FULL_REBUILD, cost_basis_method)
        return CostBasisCalculationResult(
            processed=processed,
            errored=errored,
            open_lot_states=open_lot_states,
            incremental=False,
            open_lot_persistence_scope=OpenLotPersistenceScope.COMPLETE_SNAPSHOT,
            average_cost_pool_transition=None,
        )

    async def _load_incoming_transaction(
        self,
        *,
        transaction: BookedTransaction,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
    ) -> dict[str, Any]:
        transaction_raw = build_cost_basis_engine_input(transaction)
        if instrument is not None:
            self._attach_instrument_metadata([transaction_raw], instrument)
        enriched: list[dict[str, Any]] = await enrich_cost_basis_transactions_with_fx(
            transactions=[transaction_raw],
            portfolio_base_currency=portfolio_base_currency,
            fx_rates=self._fx_rates,
        )
        return enriched[0]

    async def _get_compatible_average_cost_pool_checkpoint(
        self,
        transaction: BookedTransaction,
    ) -> AverageCostPoolCheckpointRecord | None:
        record = await self._average_cost_pools.get_average_cost_pool_checkpoint_record(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
        )
        if record is None or not record.checkpoint.is_compatible(
            portfolio_id=transaction.portfolio_id,
            instrument_id=transaction.instrument_id,
            security_id=transaction.security_id,
        ):
            return None
        if record.checkpoint.quantity > Decimal(0) and record.representative_transaction is None:
            return None
        return record

    @staticmethod
    def _load_average_cost_pool_checkpoint_transaction(
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
            CostBasisCalculationCoordinator._attach_instrument_metadata(
                [transaction_raw], instrument
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
            existing_sources_after = remaining_states.pop(representative_source_id, None)
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
        transaction: BookedTransaction,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
        required_fifo_quantity: Decimal | None,
    ) -> list[dict[str, Any]]:
        if required_fifo_quantity is None:
            records = await self._lot_states.get_open_lot_checkpoint_records(
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
            )
        else:
            records = await self._lot_states.get_fifo_disposal_lot_checkpoint_records(
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
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
            self._attach_instrument_metadata(checkpoint_transactions, instrument)
        return checkpoint_transactions

    async def _load_cost_basis_transactions(
        self,
        *,
        transaction: BookedTransaction,
        portfolio_base_currency: str,
        instrument: CostBasisInstrumentReference | None,
    ) -> list[dict[str, Any]]:
        history = await self._transactions.get_transaction_history(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            exclude_id=transaction.transaction_id,
        )
        all_transactions_raw = [
            *(build_cost_basis_engine_input(item) for item in history),
            build_cost_basis_engine_input(transaction),
        ]
        if instrument is not None:
            self._attach_instrument_metadata(all_transactions_raw, instrument)
        enriched: list[dict[str, Any]] = await enrich_cost_basis_transactions_with_fx(
            transactions=all_transactions_raw,
            portfolio_base_currency=portfolio_base_currency,
            fx_rates=self._fx_rates,
        )
        return enriched

    @staticmethod
    def _attach_instrument_metadata(
        transactions: list[dict[str, Any]],
        instrument: CostBasisInstrumentReference,
    ) -> None:
        for transaction in transactions:
            transaction["product_type"] = instrument.product_type
            transaction["asset_class"] = instrument.asset_class

    def _record_execution(
        self,
        mode: CostBasisExecutionMode,
        cost_basis_method: CostBasisMethod,
    ) -> None:
        if self._observer is not None:
            self._observer.record_execution(mode, cost_basis_method.value)

    def _record_restored_open_lots(
        self,
        *,
        cost_basis_method: CostBasisMethod,
        lot_count: int,
    ) -> None:
        if self._observer is not None:
            self._observer.record_restored_open_lots(
                cost_basis_method=cost_basis_method.value,
                lot_count=lot_count,
            )
