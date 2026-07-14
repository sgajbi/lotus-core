"""Stage cost-basis effects inside the unified transaction-processing boundary."""

import logging
from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, List, cast

from portfolio_common.config import (
    KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
    KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod, normalize_cost_basis_method
from portfolio_common.domain.decimal_amount import decimal_or_none
from portfolio_common.domain.transaction.fee_components import resolve_transaction_trade_fee
from portfolio_common.domain.transaction.type_registry import get_transaction_type_definition
from portfolio_common.events import InstrumentEvent, TransactionEvent, event_business_payload
from portfolio_common.monitoring import (
    BUY_LIFECYCLE_STAGE_TOTAL,
    SELL_LIFECYCLE_STAGE_TOTAL,
)
from portfolio_common.outbox_repository import OutboxRepository

from ..application import (
    CorporateActionReconciliationCoordinator,
    CostBasisTimelineProcessor,
    build_cost_basis_timeline_processor,
)
from ..application.cost_basis_processing import CostProcessingRoute
from ..domain.cost_basis import (
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    AverageCostPoolTransition,
    CostBasisProcessingCheckpoint,
    OpenLotState,
    transaction_order_key,
)
from ..domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from ..domain.transaction import (
    ADJUSTMENT_TRANSACTION_TYPE,
    assert_cash_entry_mode_supported,
    assert_upstream_cash_leg_pairing,
    build_generated_settlement_cash_leg,
    is_upstream_provided_cash_entry_mode,
    should_generate_settlement_cash_leg,
)
from ..domain.transaction.fx import (
    assert_fx_processed_transaction_valid,
    build_fx_contract_instrument,
    build_fx_processed_transaction,
)
from ..ports import (
    CorporateActionReconciliationObserver,
    CostBasisCalculationObserver,
)
from .booked_transaction_event_mapper import (
    to_booked_transaction,
    to_transaction_event,
    with_booked_transaction_fields,
)
from .cost_metrics import COST_PROCESSING_EXECUTION_TOTAL, COST_PROCESSING_OPEN_LOTS_RESTORED
from .cost_repository import AverageCostPoolCheckpointRecord, CostCalculatorRepository
from .fx_event_mapper import to_fx_contract_instrument_event

logger = logging.getLogger(__name__)
LOT_OPENING_BEHAVIORS = {
    "basis_allocation_in",
    "open_lot",
    "open_rights_lot",
    "preserve_or_restate_lot",
    "transfer_basis_in",
}
LOT_STATE_MUTATING_BEHAVIORS = LOT_OPENING_BEHAVIORS | {
    "consume_lot",
    "consume_rights_lot",
    "partial_basis_transfer",
    "preserve_or_consume_lot",
    "transfer_basis_out",
}
STATE_DEPENDENT_LOT_BEHAVIORS = LOT_STATE_MUTATING_BEHAVIORS - LOT_OPENING_BEHAVIORS
INCREMENTAL_SAFE_LOT_BEHAVIORS = LOT_OPENING_BEHAVIORS | STATE_DEPENDENT_LOT_BEHAVIORS | {"none"}
AVERAGE_COST_POOL_LOT_BEHAVIORS = {"open_lot", "consume_lot"}


class OpenLotStateUpdateScope(str, Enum):
    COMPLETE_SNAPSHOT = "complete_snapshot"
    SELECTED_LOTS = "selected_lots"
    AVERAGE_COST_POOL = "average_cost_pool"


@dataclass(frozen=True, slots=True)
class CostEngineCalculation:
    processed: list[EngineTransaction]
    errored: list[Any]
    open_lot_states: dict[str, OpenLotState]
    incremental: bool
    open_lot_state_update_scope: OpenLotStateUpdateScope
    average_cost_pool_transition: AverageCostPoolTransition | None


def _normalize_event_code(value: object) -> str:
    return str(value or "").strip().upper()


def _transaction_lot_behavior(transaction_type: object) -> str:
    definition = get_transaction_type_definition(_normalize_event_code(transaction_type))
    return definition.lot_behavior if definition is not None else "unknown"


def _normalize_fee_amount(value: object, *, field_name: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal(0)
    amount = cast(Decimal | None, decimal_or_none(value))
    if amount is None:
        raise ValueError(f"{field_name} must be numeric.")
    return amount


normalize_cost_event_code = _normalize_event_code
normalize_cost_fee_amount = _normalize_fee_amount


FEE_COMPONENT_FIELDS = ("brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees")


def _pop_fee_components(event_dict: dict[str, Any]) -> dict[str, object]:
    return {field_name: event_dict.pop(field_name, None) for field_name in FEE_COMPONENT_FIELDS}


def _has_fee_components(fee_components: dict[str, object]) -> bool:
    return any(value is not None for value in fee_components.values())


def _normalize_fee_components(fee_components: dict[str, object]) -> dict[str, Decimal]:
    return {
        field_name: _normalize_fee_amount(value, field_name=field_name)
        for field_name, value in fee_components.items()
    }


def _apply_engine_fee_fields(
    *,
    event_dict: dict[str, Any],
    resolved_trade_fee: Decimal,
    normalized_components: dict[str, Decimal],
    has_fee_components: bool,
) -> None:
    if has_fee_components:
        event_dict["fees"] = {
            field_name: str(amount) for field_name, amount in normalized_components.items()
        }
        event_dict["trade_fee"] = str(resolved_trade_fee)
        return

    if resolved_trade_fee and resolved_trade_fee > 0:
        event_dict["fees"] = {"brokerage": str(resolved_trade_fee)}
        event_dict["trade_fee"] = str(resolved_trade_fee)
        return

    event_dict["trade_fee"] = "0"


class FxRateNotFoundError(Exception):
    """Raised when a required FX rate is not yet available in the database."""

    pass


class UpstreamCashLegUnavailableError(Exception):
    """Raised when a required upstream cash leg is not yet persisted."""

    pass


class CostCalculationWorkflow:
    """
    Calculates and stages cost, lot, transaction, instrument, and outbox effects.

    Database transaction, idempotency, retry, and delivery lifecycle ownership remain outside this
    workflow.
    """

    _cost_basis_observer: CostBasisCalculationObserver | None = None
    _corporate_action_reconciliation_observer: CorporateActionReconciliationObserver | None = None

    def configure_cost_basis_observer(self, observer: CostBasisCalculationObserver) -> None:
        """Attach infrastructure observability without changing legacy delivery construction."""
        self._cost_basis_observer = observer

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

    async def build_average_cost_pool_rebuild_plan(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        repo: CostCalculatorRepository,
    ) -> AverageCostPoolRebuildPlan:
        portfolio = await repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} was not found")
        cost_basis_method = normalize_cost_basis_method(portfolio.cost_basis_method)
        if cost_basis_method is not CostBasisMethod.AVCO:
            raise ValueError("Average cost pool rebuild requires an AVCO portfolio")

        instrument = await repo.get_instrument(security_id)
        if instrument is None:
            raise ValueError(f"Instrument {security_id} was not found")
        history = await repo.get_transaction_history(
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
        if not history:
            raise ValueError("Average cost pool rebuild requires transaction history")

        history_raw = [
            self._transform_event_for_engine(TransactionEvent.model_validate(transaction))
            for transaction in history
        ]
        self._attach_instrument_metadata(transactions=history_raw, instrument=instrument)
        enriched_history = await self._enrich_transactions_with_fx(
            transactions=history_raw,
            portfolio_base_currency=portfolio.base_currency,
            repo=repo,
        )
        processed, errored, source_states = self._get_cost_basis_timeline_processor(
            CostBasisMethod.AVCO
        ).process_transactions(existing_transactions_raw=[], new_transactions_raw=enriched_history)
        self._raise_for_transaction_engine_errors(errored=errored)
        latest_transaction = max(processed, key=transaction_order_key)
        source_transactions = tuple(
            transaction
            for transaction in processed
            if _transaction_lot_behavior(transaction.transaction_type) in LOT_OPENING_BEHAVIORS
        )
        checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
            portfolio_id=portfolio_id,
            instrument_id=latest_transaction.instrument_id,
            security_id=security_id,
            states_by_source_transaction_id=source_states,
        )
        return AverageCostPoolRebuildPlan(
            checkpoint=checkpoint,
            processing_checkpoint=CostBasisProcessingCheckpoint.from_transaction(
                latest_transaction,
                cost_basis_method=CostBasisMethod.AVCO,
            ),
            source_transactions=source_transactions,
            source_states=source_states,
        )

    @staticmethod
    def _record_lifecycle_stage(transaction_type: str, stage: str, status: str) -> None:
        normalized_type = _normalize_event_code(transaction_type)
        if normalized_type == "BUY":
            BUY_LIFECYCLE_STAGE_TOTAL.labels(stage, status).inc()
        if normalized_type == "SELL":
            SELL_LIFECYCLE_STAGE_TOTAL.labels(stage, status).inc()

    def _transform_event_for_engine(self, event: TransactionEvent) -> dict:
        """
        Transforms a TransactionEvent into a raw dictionary suitable for the
        cost-calculator-service engine package, converting fee fields to a Fees object structure.
        """
        event_dict = cast(dict[str, Any], event.model_dump(mode="python"))
        trade_fee = _normalize_fee_amount(
            event_dict.pop("trade_fee", "0"),
            field_name="trade_fee",
        )
        fee_components = _pop_fee_components(event_dict)
        has_fee_components = _has_fee_components(fee_components)
        normalized_components = _normalize_fee_components(fee_components)
        resolved_trade_fee = resolve_transaction_trade_fee(
            trade_fee,
            normalized_components if has_fee_components else {},
        )
        _apply_engine_fee_fields(
            event_dict=event_dict,
            resolved_trade_fee=resolved_trade_fee,
            normalized_components=normalized_components,
            has_fee_components=has_fee_components,
        )

        return event_dict

    async def _enrich_transactions_with_fx(
        self,
        transactions: List[dict[str, Any]],
        portfolio_base_currency: str,
        repo: CostCalculatorRepository,
    ) -> List[dict[str, Any]]:
        """Attach latest-on-or-before FX rates using one bounded read per currency pair."""
        portfolio_base_currency = _normalize_event_code(portfolio_base_currency)
        transactions_by_pair: dict[
            tuple[str, str],
            list[tuple[dict[str, Any], date]],
        ] = {}
        for txn_raw in transactions:
            trade_currency = _normalize_event_code(txn_raw.get("trade_currency"))
            txn_raw["trade_currency"] = trade_currency
            txn_raw["portfolio_base_currency"] = portfolio_base_currency

            if trade_currency == portfolio_base_currency:
                continue

            transaction_date_value = txn_raw["transaction_date"]
            transaction_date = (
                transaction_date_value.date()
                if isinstance(transaction_date_value, datetime)
                else datetime.fromisoformat(
                    str(transaction_date_value).replace("Z", "+00:00")
                ).date()
            )
            transactions_by_pair.setdefault((trade_currency, portfolio_base_currency), []).append(
                (txn_raw, transaction_date)
            )

        for (trade_currency, base_currency), pair_transactions in transactions_by_pair.items():
            requested_dates = [transaction_date for _, transaction_date in pair_transactions]
            fx_rates = await repo.get_fx_rate_window(
                from_currency=trade_currency,
                to_currency=base_currency,
                start_date=min(requested_dates),
                end_date=max(requested_dates),
            )
            rate_dates = [fx_rate.effective_date for fx_rate in fx_rates]
            for txn_raw, transaction_date in pair_transactions:
                effective_rate_index = bisect_right(rate_dates, transaction_date) - 1
                if effective_rate_index < 0:
                    raise FxRateNotFoundError(
                        f"FX rate for {trade_currency}->{base_currency} on "
                        f"{txn_raw['transaction_date']} not found. Retrying..."
                    )
                txn_raw["transaction_fx_rate"] = fx_rates[effective_rate_index].rate

        return transactions

    async def _build_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        route: CostProcessingRoute,
        portfolio: Any,
        instrument: Any,
        repo: CostCalculatorRepository,
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
            cost_basis_method=cost_basis_method,
        )

    async def _build_fx_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        repo: CostCalculatorRepository,
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]:
        processed_transaction = build_fx_processed_transaction(to_booked_transaction(event))
        assert_fx_processed_transaction_valid(processed_transaction)
        processed_event = with_booked_transaction_fields(event, processed_transaction)
        await repo.create_or_update_transaction_event(processed_event)
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
        portfolio: Any,
        instrument: Any,
        repo: CostCalculatorRepository,
        cost_basis_method: CostBasisMethod,
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]:
        await repo.acquire_cost_basis_processing_lock(event.portfolio_id, event.security_id)
        calculation = await self._calculate_cost_basis(
            event=event,
            event_transaction_type=event_transaction_type,
            portfolio_base_currency=portfolio.base_currency,
            instrument=instrument,
            repo=repo,
            cost_basis_method=cost_basis_method,
        )

        new_transaction_ids = {event.transaction_id}
        self._raise_for_transaction_engine_errors(errored=calculation.errored)
        events_to_publish = await self._persist_affected_processed_transactions(
            processed=calculation.processed,
            new_transaction_ids=new_transaction_ids,
            repo=repo,
        )
        await self._update_open_lot_states_if_required(
            event=event,
            event_transaction_type=event_transaction_type,
            open_lot_states=calculation.open_lot_states,
            repo=repo,
            incremental=calculation.incremental,
            update_scope=calculation.open_lot_state_update_scope,
            cost_basis_method=cost_basis_method,
            average_cost_pool_transition=calculation.average_cost_pool_transition,
        )
        await self._persist_cost_basis_processing_checkpoint(
            processed=calculation.processed,
            cost_basis_method=cost_basis_method,
            repo=repo,
        )

        return events_to_publish, []

    async def _calculate_cost_basis(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        portfolio_base_currency: str,
        instrument: Any,
        repo: CostCalculatorRepository,
        cost_basis_method: CostBasisMethod,
    ) -> CostEngineCalculation:
        checkpoint = await repo.get_cost_basis_processing_checkpoint(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
        )
        lot_behavior = _transaction_lot_behavior(event_transaction_type)
        if checkpoint is not None and lot_behavior in INCREMENTAL_SAFE_LOT_BEHAVIORS:
            incoming_raw = await self._load_incoming_cost_basis_transaction(
                event=event,
                portfolio_base_currency=portfolio_base_currency,
                instrument=instrument,
                repo=repo,
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
                            repo=repo,
                        )
                    )
                    if average_cost_pool_record is None:
                        return await self._calculate_full_cost_rebuild(
                            event=event,
                            portfolio_base_currency=portfolio_base_currency,
                            instrument=instrument,
                            repo=repo,
                            cost_basis_method=cost_basis_method,
                        )
                initial_open_lots_raw = []
                open_lot_state_update_scope = OpenLotStateUpdateScope.COMPLETE_SNAPSHOT
                if average_cost_pool_record is not None:
                    initial_open_lots_raw = self._load_average_cost_pool_checkpoint_transaction(
                        record=average_cost_pool_record,
                        portfolio_base_currency=portfolio_base_currency,
                        instrument=instrument,
                    )
                    open_lot_state_update_scope = OpenLotStateUpdateScope.AVERAGE_COST_POOL
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
                        repo=repo,
                        required_fifo_quantity=required_fifo_quantity,
                    )
                    if required_fifo_quantity is not None:
                        open_lot_state_update_scope = OpenLotStateUpdateScope.SELECTED_LOTS
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
                return CostEngineCalculation(
                    processed=processed,
                    errored=errored,
                    open_lot_states=open_lot_states,
                    incremental=True,
                    open_lot_state_update_scope=open_lot_state_update_scope,
                    average_cost_pool_transition=average_cost_pool_transition,
                )

        return await self._calculate_full_cost_rebuild(
            event=event,
            portfolio_base_currency=portfolio_base_currency,
            instrument=instrument,
            repo=repo,
            cost_basis_method=cost_basis_method,
        )

    async def _calculate_full_cost_rebuild(
        self,
        *,
        event: TransactionEvent,
        portfolio_base_currency: str,
        instrument: Any,
        repo: CostCalculatorRepository,
        cost_basis_method: CostBasisMethod,
    ) -> CostEngineCalculation:
        all_transactions_raw = await self._load_cost_basis_transactions(
            event=event,
            portfolio_base_currency=portfolio_base_currency,
            instrument=instrument,
            repo=repo,
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
        return CostEngineCalculation(
            processed=processed,
            errored=errored,
            open_lot_states=open_lot_states,
            incremental=False,
            open_lot_state_update_scope=OpenLotStateUpdateScope.COMPLETE_SNAPSHOT,
            average_cost_pool_transition=None,
        )

    async def _load_incoming_cost_basis_transaction(
        self,
        *,
        event: TransactionEvent,
        portfolio_base_currency: str,
        instrument: Any,
        repo: CostCalculatorRepository,
    ) -> dict[str, Any]:
        event_raw = self._transform_event_for_engine(event)
        if instrument is not None:
            self._attach_instrument_metadata(transactions=[event_raw], instrument=instrument)
        enriched = await self._enrich_transactions_with_fx(
            transactions=[event_raw],
            portfolio_base_currency=portfolio_base_currency,
            repo=repo,
        )
        return enriched[0]

    @staticmethod
    async def _get_compatible_average_cost_pool_checkpoint(
        *,
        event: TransactionEvent,
        repo: CostCalculatorRepository,
    ) -> AverageCostPoolCheckpointRecord | None:
        record = await repo.get_average_cost_pool_checkpoint_record(
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
        instrument: Any,
    ) -> list[dict[str, Any]]:
        checkpoint = record.checkpoint
        if checkpoint.quantity == Decimal(0):
            return []
        if record.representative_transaction is None:
            raise ValueError("Open average cost pool has no representative transaction")
        transaction_raw = self._transform_event_for_engine(
            TransactionEvent.model_validate(record.representative_transaction)
        )
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
        instrument: Any,
        repo: CostCalculatorRepository,
        required_fifo_quantity: Decimal | None = None,
    ) -> list[dict[str, Any]]:
        if required_fifo_quantity is None:
            records = await repo.get_open_lot_checkpoint_records(
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
            )
        else:
            records = await repo.get_fifo_disposal_lot_checkpoint_records(
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
                required_quantity=required_fifo_quantity,
            )
        checkpoint_transactions: list[dict[str, Any]] = []
        for record in records:
            transaction_raw = self._transform_event_for_engine(
                TransactionEvent.model_validate(record.transaction)
            )
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
        instrument: Any,
        repo: CostCalculatorRepository,
    ) -> list[dict[str, Any]]:
        history_db = await repo.get_transaction_history(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            exclude_id=event.transaction_id,
        )
        history_raw = [
            self._transform_event_for_engine(TransactionEvent.model_validate(t)) for t in history_db
        ]
        event_raw = self._transform_event_for_engine(event)
        all_transactions_raw = [*history_raw, event_raw]
        if instrument is not None:
            self._attach_instrument_metadata(
                transactions=all_transactions_raw,
                instrument=instrument,
            )
        return await self._enrich_transactions_with_fx(
            transactions=all_transactions_raw,
            portfolio_base_currency=portfolio_base_currency,
            repo=repo,
        )

    async def _persist_affected_processed_transactions(
        self,
        *,
        processed: list[Any],
        new_transaction_ids: set[str],
        repo: CostCalculatorRepository,
    ) -> list[TransactionEvent]:
        first_affected_index = next(
            (
                index
                for index, transaction in enumerate(processed)
                if transaction.transaction_id in new_transaction_ids
            ),
            None,
        )
        if first_affected_index is None:
            raise ValueError("Processed transaction timeline omitted the incoming transaction")

        events_to_publish: list[TransactionEvent] = []
        for processed_transaction in processed[first_affected_index:]:
            persisted_event = await self._persist_processed_transaction(
                processed_transaction=processed_transaction,
                repo=repo,
            )
            if processed_transaction.transaction_id in new_transaction_ids:
                events_to_publish.append(persisted_event)
        return events_to_publish

    @staticmethod
    async def _update_open_lot_states_if_required(
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        open_lot_states: dict[str, OpenLotState],
        repo: CostCalculatorRepository,
        incremental: bool,
        update_scope: OpenLotStateUpdateScope,
        cost_basis_method: CostBasisMethod,
        average_cost_pool_transition: AverageCostPoolTransition | None,
    ) -> None:
        if average_cost_pool_transition is not None:
            await repo.apply_average_cost_pool_transition(average_cost_pool_transition)
            return

        lot_behavior = _transaction_lot_behavior(event_transaction_type)
        mutates_lot_state = lot_behavior in LOT_STATE_MUTATING_BEHAVIORS
        incremental_opening = incremental and lot_behavior in LOT_OPENING_BEHAVIORS
        should_update_lot_states = not incremental or (
            mutates_lot_state and not incremental_opening
        )
        if should_update_lot_states:
            update_lot_states = (
                repo.update_selected_open_lot_states
                if update_scope is OpenLotStateUpdateScope.SELECTED_LOTS
                else repo.update_open_lot_states
            )
            await update_lot_states(
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
                states_by_source_transaction_id=open_lot_states,
            )

        should_persist_complete_average_cost_pool = cost_basis_method is CostBasisMethod.AVCO and (
            not incremental or (mutates_lot_state and not incremental_opening)
        )
        if should_persist_complete_average_cost_pool:
            await repo.upsert_average_cost_pool_checkpoint(
                AverageCostPoolCheckpoint.from_open_lot_states(
                    portfolio_id=event.portfolio_id,
                    instrument_id=event.instrument_id,
                    security_id=event.security_id,
                    states_by_source_transaction_id=open_lot_states,
                )
            )

    @staticmethod
    async def _persist_cost_basis_processing_checkpoint(
        *,
        processed: list[EngineTransaction],
        cost_basis_method: CostBasisMethod,
        repo: CostCalculatorRepository,
    ) -> None:
        latest_transaction = max(processed, key=transaction_order_key)
        await repo.upsert_cost_basis_processing_checkpoint(
            CostBasisProcessingCheckpoint.from_transaction(
                latest_transaction,
                cost_basis_method=cost_basis_method,
            )
        )

    @staticmethod
    def _attach_instrument_metadata(
        *,
        transactions: list[dict[str, Any]],
        instrument: Any,
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

    async def _persist_processed_transaction(
        self,
        *,
        processed_transaction: Any,
        repo: CostCalculatorRepository,
    ) -> TransactionEvent:
        self._record_lifecycle_stage(
            processed_transaction.transaction_type, "persist_transaction_costs", "attempt"
        )
        updated_txn = await repo.update_transaction_costs(processed_transaction)
        if updated_txn is None:
            raise ValueError(
                "Canonical transaction row was not found during cost persistence: "
                f"{processed_transaction.transaction_id}"
            )
        await repo.replace_transaction_cost_breakdown(processed_transaction)
        self._record_lifecycle_stage(
            processed_transaction.transaction_type, "persist_transaction_costs", "success"
        )

        if (
            _transaction_lot_behavior(processed_transaction.transaction_type)
            in LOT_OPENING_BEHAVIORS
        ):
            await self._persist_open_lot_state(
                processed_transaction=processed_transaction,
                repo=repo,
            )
        if processed_transaction.transaction_type == "BUY":
            await self._persist_accrued_income_offset(
                processed_transaction=processed_transaction,
                repo=repo,
            )
        if processed_transaction.transaction_type == "SELL":
            self._log_processed_transaction_state(
                log_event="sell_state_persisted",
                processed_transaction=processed_transaction,
            )

        if processed_transaction.fees and processed_transaction.fees.total_fees > 0:
            updated_txn.trade_fee = processed_transaction.fees.total_fees
        else:
            updated_txn.trade_fee = Decimal(0)
        return TransactionEvent.model_validate(updated_txn)

    async def _persist_open_lot_state(
        self,
        *,
        processed_transaction: Any,
        repo: CostCalculatorRepository,
    ) -> None:
        self._record_lifecycle_stage(
            processed_transaction.transaction_type, "persist_lot_state", "attempt"
        )
        await repo.upsert_buy_lot_state(processed_transaction)
        self._record_lifecycle_stage(
            processed_transaction.transaction_type, "persist_lot_state", "success"
        )
        self._log_processed_transaction_state(
            log_event="open_lot_state_persisted",
            processed_transaction=processed_transaction,
        )

    async def _persist_accrued_income_offset(
        self,
        *,
        processed_transaction: Any,
        repo: CostCalculatorRepository,
    ) -> None:
        self._record_lifecycle_stage(
            processed_transaction.transaction_type,
            "persist_accrued_offset_state",
            "attempt",
        )
        await repo.upsert_accrued_income_offset_state(processed_transaction)
        self._record_lifecycle_stage(
            processed_transaction.transaction_type,
            "persist_accrued_offset_state",
            "success",
        )

    @staticmethod
    def _log_processed_transaction_state(
        *,
        log_event: str,
        processed_transaction: Any,
    ) -> None:
        logger.info(
            log_event,
            extra={
                "transaction_id": processed_transaction.transaction_id,
                "economic_event_id": getattr(processed_transaction, "economic_event_id", None),
                "linked_transaction_group_id": getattr(
                    processed_transaction, "linked_transaction_group_id", None
                ),
                "calculation_policy_id": getattr(
                    processed_transaction, "calculation_policy_id", None
                ),
                "calculation_policy_version": getattr(
                    processed_transaction, "calculation_policy_version", None
                ),
            },
        )

    async def _build_emitted_transaction_events(
        self,
        *,
        events_to_publish: list[TransactionEvent],
        repo: CostCalculatorRepository,
        correlation_id: str,
    ) -> list[TransactionEvent]:
        emitted_events: list[TransactionEvent] = []
        corporate_action_reconciliation = CorporateActionReconciliationCoordinator(
            repo,
            observer=self._corporate_action_reconciliation_observer,
        )
        for processed_event in events_to_publish:
            await self._validate_upstream_cash_leg(processed_event=processed_event, repo=repo)
            booked_transaction = to_booked_transaction(processed_event)
            generated_cash_leg = None
            if should_generate_settlement_cash_leg(booked_transaction):
                generated_cash_leg = to_transaction_event(
                    build_generated_settlement_cash_leg(booked_transaction),
                    correlation_id=None,
                    traceparent=None,
                )
                await repo.create_or_update_transaction_event(generated_cash_leg)
                processed_event = with_booked_transaction_fields(
                    processed_event,
                    replace(
                        booked_transaction,
                        external_cash_transaction_id=generated_cash_leg.transaction_id,
                    ),
                )
                await repo.create_or_update_transaction_event(processed_event)
            emitted_events.append(processed_event)
            if generated_cash_leg is not None:
                emitted_events.append(generated_cash_leg)

            await corporate_action_reconciliation.reconcile(
                to_booked_transaction(processed_event),
                correlation_id=correlation_id,
            )
        return emitted_events

    async def _validate_upstream_cash_leg(
        self,
        *,
        processed_event: TransactionEvent,
        repo: CostCalculatorRepository,
    ) -> None:
        assert_cash_entry_mode_supported(to_booked_transaction(processed_event))
        if not self._requires_upstream_cash_leg_validation(processed_event):
            return

        external_cash_id = self._required_external_cash_transaction_id(processed_event)
        cash_leg = await self._load_upstream_cash_leg(
            external_cash_id=external_cash_id,
            processed_event=processed_event,
            repo=repo,
        )
        assert_upstream_cash_leg_pairing(
            to_booked_transaction(processed_event),
            to_booked_transaction(cash_leg),
        )

    @staticmethod
    def _requires_upstream_cash_leg_validation(processed_event: TransactionEvent) -> bool:
        return (
            processed_event.cash_entry_mode is not None
            and is_upstream_provided_cash_entry_mode(processed_event.cash_entry_mode)
            and _normalize_event_code(processed_event.transaction_type)
            != ADJUSTMENT_TRANSACTION_TYPE
        )

    @staticmethod
    def _required_external_cash_transaction_id(processed_event: TransactionEvent) -> str:
        external_cash_id = (processed_event.external_cash_transaction_id or "").strip()
        if external_cash_id:
            return external_cash_id
        raise ValueError("UPSTREAM_PROVIDED requires external_cash_transaction_id on product leg.")

    @staticmethod
    async def _load_upstream_cash_leg(
        *,
        external_cash_id: str,
        processed_event: TransactionEvent,
        repo: CostCalculatorRepository,
    ) -> TransactionEvent:
        cash_leg_db = await repo.get_transaction_by_id(
            external_cash_id, portfolio_id=processed_event.portfolio_id
        )
        if cash_leg_db is None:
            raise UpstreamCashLegUnavailableError(
                f"Cash leg {external_cash_id} not found for portfolio "
                f"{processed_event.portfolio_id}."
            )
        return TransactionEvent.model_validate(cash_leg_db)

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
            self._record_lifecycle_stage(publish_event.transaction_type, "emit_outbox", "success")

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
