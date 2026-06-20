# src/services/calculators/cost_calculator_service/app/consumer.py
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, List

from confluent_kafka import Message
from portfolio_common.config import (
    KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
    KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
)
from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method
from portfolio_common.db import get_async_db_session
from portfolio_common.decimal_amounts import decimal_or_none
from portfolio_common.events import InstrumentEvent, TransactionEvent
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.monitoring import BUY_LIFECYCLE_STAGE_TOTAL, SELL_LIFECYCLE_STAGE_TOTAL
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.transaction_domain import (
    DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE,
    assert_ca_bundle_a_transaction_valid,
    assert_fx_processed_event_valid,
    assert_portfolio_flow_cash_entry_mode_allowed,
    assert_upstream_cash_leg_pairing,
    build_auto_generated_adjustment_cash_leg,
    build_fx_contract_instrument_event,
    build_fx_processed_event,
    enrich_buy_transaction_metadata,
    enrich_dividend_transaction_metadata,
    enrich_fx_transaction_metadata,
    enrich_interest_transaction_metadata,
    enrich_sell_transaction_metadata,
    evaluate_ca_bundle_a_reconciliation,
    find_missing_ca_bundle_a_dependencies,
    is_ca_bundle_a_transaction_type,
    is_upstream_provided_cash_entry_mode,
    should_auto_generate_cash_leg,
)
from portfolio_common.transaction_fee_components import resolve_transaction_trade_fee
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .cost_engine.processing.cost_basis_strategies import (
    AverageCostBasisStrategy,
    FIFOBasisStrategy,
)
from .cost_engine.processing.cost_calculator import CostCalculator
from .cost_engine.processing.disposition_engine import DispositionEngine
from .cost_engine.processing.error_reporter import ErrorReporter
from .cost_engine.processing.parser import TransactionParser
from .cost_engine.processing.sorter import TransactionSorter
from .repository import CostCalculatorRepository
from .transaction_processor import TransactionProcessor

logger = logging.getLogger(__name__)
SERVICE_NAME = "cost-calculator"
ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"


def _normalize_event_code(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_fee_amount(value: object, *, field_name: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal(0)
    amount = decimal_or_none(value)
    if amount is None:
        raise ValueError(f"{field_name} must be numeric.")
    return amount


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


def _message_value(msg: Message) -> str:
    return msg.value().decode("utf-8")


def _message_event_id(msg: Message) -> str:
    return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"


class FxRateNotFoundError(Exception):
    """Raised when a required FX rate is not yet available in the database."""

    pass


class PortfolioNotFoundError(Exception):
    """Raised when the portfolio for a transaction is not yet in the database."""

    pass


class UpstreamCashLegUnavailableError(Exception):
    """Raised when a required upstream cash leg is not yet persisted."""

    pass


class CostCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction events, calculates costs/realized P&L,
    persists updates, and emits a full TransactionEvent downstream.
    """

    def _get_transaction_processor(
        self, cost_basis_method: str | CostBasisMethod = CostBasisMethod.FIFO
    ) -> TransactionProcessor:
        """
        Builds and returns an instance of the TransactionProcessor, injecting
        the specified cost basis strategy.
        """
        error_reporter = ErrorReporter()
        parser = TransactionParser(error_reporter=error_reporter)
        sorter = TransactionSorter()

        resolved_method = normalize_cost_basis_method(cost_basis_method)
        if resolved_method is CostBasisMethod.AVCO:
            strategy = AverageCostBasisStrategy()
            logger.debug("Using AVCO strategy for cost basis calculation.")
        else:
            strategy = FIFOBasisStrategy()
            logger.debug("Using FIFO strategy for cost basis calculation.")

        disposition_engine = DispositionEngine(cost_basis_strategy=strategy)
        cost_calculator = CostCalculator(
            disposition_engine=disposition_engine, error_reporter=error_reporter
        )
        return TransactionProcessor(
            parser=parser,
            sorter=sorter,
            disposition_engine=disposition_engine,
            cost_calculator=cost_calculator,
            error_reporter=error_reporter,
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
        event_dict = event.model_dump(mode="json")
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
        """
        Iterates through transactions, fetching and attaching FX rates for cross-currency trades.
        """
        portfolio_base_currency = _normalize_event_code(portfolio_base_currency)
        for txn_raw in transactions:
            trade_currency = _normalize_event_code(txn_raw.get("trade_currency"))
            txn_raw["trade_currency"] = trade_currency
            txn_raw["portfolio_base_currency"] = portfolio_base_currency

            if trade_currency == portfolio_base_currency:
                continue

            fx_rate = await repo.get_fx_rate(
                from_currency=trade_currency,
                to_currency=portfolio_base_currency,
                a_date=datetime.fromisoformat(
                    txn_raw["transaction_date"].replace("Z", "+00:00")
                ).date(),
            )

            if not fx_rate:
                raise FxRateNotFoundError(
                    f"FX rate for {txn_raw['trade_currency']}->{portfolio_base_currency} on "
                    f"{txn_raw['transaction_date']} not found. Retrying..."
                )

            txn_raw["transaction_fx_rate"] = fx_rate.rate

        return transactions

    async def _prepare_transaction_event(
        self,
        event: TransactionEvent,
        portfolio: Any,
    ) -> tuple[TransactionEvent, str, CostBasisMethod]:
        cost_basis_method = normalize_cost_basis_method(portfolio.cost_basis_method)
        event = enrich_buy_transaction_metadata(event)
        event = enrich_sell_transaction_metadata(event, cost_basis_method=cost_basis_method)
        event = enrich_fx_transaction_metadata(event)
        event = enrich_dividend_transaction_metadata(event)
        event = enrich_interest_transaction_metadata(event)
        if is_ca_bundle_a_transaction_type(event.transaction_type):
            assert_ca_bundle_a_transaction_valid(event)
        return event, _normalize_event_code(event.transaction_type), cost_basis_method

    async def _build_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        portfolio: Any,
        instrument: Any,
        repo: CostCalculatorRepository,
        cost_basis_method: CostBasisMethod,
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]:
        if event_transaction_type == ADJUSTMENT_TRANSACTION_TYPE:
            return [event], []
        if event_transaction_type in {"FX_SPOT", "FX_FORWARD", "FX_SWAP"}:
            return await self._build_fx_events_to_publish(event=event, repo=repo)
        return await self._build_cost_engine_events_to_publish(
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
        processed_event = build_fx_processed_event(event)
        assert_fx_processed_event_valid(processed_event)
        await repo.create_or_update_transaction_event(processed_event)
        instrument_events = []
        contract_instrument = build_fx_contract_instrument_event(processed_event)
        if contract_instrument is not None:
            instrument_events.append(contract_instrument)
        return [processed_event], instrument_events

    async def _build_cost_engine_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        portfolio: Any,
        instrument: Any,
        repo: CostCalculatorRepository,
        cost_basis_method: CostBasisMethod,
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]:
        history_db = await repo.get_transaction_history(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            exclude_id=event.transaction_id,
        )
        history_raw = [
            self._transform_event_for_engine(TransactionEvent.model_validate(t)) for t in history_db
        ]
        event_raw = self._transform_event_for_engine(event)
        if instrument is not None:
            self._attach_instrument_metadata(
                transactions=[*history_raw, event_raw],
                instrument=instrument,
            )

        all_transactions_raw = await self._enrich_transactions_with_fx(
            transactions=history_raw + [event_raw],
            portfolio_base_currency=portfolio.base_currency,
            repo=repo,
        )
        processed, errored, open_lot_quantities = self._get_transaction_processor(
            cost_basis_method
        ).process_transactions(
            existing_transactions_raw=[],
            new_transactions_raw=all_transactions_raw,
        )

        new_transaction_ids = {event.transaction_id}
        self._raise_for_new_transaction_engine_errors(
            errored=errored,
            new_transaction_ids=new_transaction_ids,
        )
        events_to_publish = []
        for processed_transaction in processed:
            if processed_transaction.transaction_id not in new_transaction_ids:
                continue
            events_to_publish.append(
                await self._persist_processed_transaction(
                    processed_transaction=processed_transaction,
                    repo=repo,
                )
            )

        if event_transaction_type in {"BUY", "SELL"}:
            await repo.update_lot_open_quantities(
                portfolio_id=event.portfolio_id,
                security_id=event.security_id,
                open_quantities_by_source_transaction_id=open_lot_quantities,
            )

        return events_to_publish, []

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
    def _raise_for_new_transaction_engine_errors(
        *,
        errored: list[Any],
        new_transaction_ids: set[str],
    ) -> None:
        new_errors = [e for e in errored if e.transaction_id in new_transaction_ids]
        if new_errors:
            raise ValueError(f"Transaction engine failed: {new_errors[0].error_reason}")

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
        await repo.replace_transaction_cost_breakdown(processed_transaction)
        self._record_lifecycle_stage(
            processed_transaction.transaction_type, "persist_transaction_costs", "success"
        )

        if processed_transaction.transaction_type == "BUY":
            await self._persist_buy_state(processed_transaction=processed_transaction, repo=repo)
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

    async def _persist_buy_state(
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
        self._log_processed_transaction_state(
            log_event="buy_state_persisted",
            processed_transaction=processed_transaction,
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
    ) -> list[TransactionEvent]:
        emitted_events: list[TransactionEvent] = []
        reconciled_bundle_groups: set[tuple[str, str]] = set()
        for processed_event in events_to_publish:
            await self._validate_upstream_cash_leg(processed_event=processed_event, repo=repo)
            emitted_events.append(processed_event)
            if should_auto_generate_cash_leg(processed_event):
                generated_cash_leg = build_auto_generated_adjustment_cash_leg(processed_event)
                await repo.create_or_update_transaction_event(generated_cash_leg)
                processed_event.external_cash_transaction_id = generated_cash_leg.transaction_id
                await repo.create_or_update_transaction_event(processed_event)
                emitted_events.append(generated_cash_leg)

            await self._record_bundle_a_reconciliation_diagnostics(
                processed_event=processed_event,
                repo=repo,
                reconciled_bundle_groups=reconciled_bundle_groups,
            )
        return emitted_events

    async def _validate_upstream_cash_leg(
        self,
        *,
        processed_event: TransactionEvent,
        repo: CostCalculatorRepository,
    ) -> None:
        assert_portfolio_flow_cash_entry_mode_allowed(processed_event)
        if not self._requires_upstream_cash_leg_validation(processed_event):
            return

        external_cash_id = self._required_external_cash_transaction_id(processed_event)
        cash_leg = await self._load_upstream_cash_leg(
            external_cash_id=external_cash_id,
            processed_event=processed_event,
            repo=repo,
        )
        assert_upstream_cash_leg_pairing(processed_event, cash_leg)

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

    async def _record_bundle_a_reconciliation_diagnostics(
        self,
        *,
        processed_event: TransactionEvent,
        repo: CostCalculatorRepository,
        reconciled_bundle_groups: set[tuple[str, str]],
    ) -> None:
        group_key = self._bundle_a_reconciliation_key(processed_event)
        if group_key is None:
            return
        if group_key in reconciled_bundle_groups:
            return

        linked_group, parent_ref = group_key
        group_events = await self._load_bundle_a_group_events(
            processed_event=processed_event,
            repo=repo,
            linked_group=linked_group,
            parent_ref=parent_ref,
        )
        reconciliation = evaluate_ca_bundle_a_reconciliation(
            group_events,
            basis_tolerance=DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE,
        )
        missing_dependencies = self._bundle_a_missing_dependencies(
            processed_event=processed_event,
            group_events=group_events,
        )
        self._log_bundle_a_reconciliation(
            processed_event=processed_event,
            linked_group=linked_group,
            parent_ref=parent_ref,
            reconciliation=reconciliation,
            missing_dependencies=missing_dependencies,
        )
        reconciled_bundle_groups.add(group_key)

    @staticmethod
    def _bundle_a_reconciliation_key(processed_event: TransactionEvent) -> tuple[str, str] | None:
        if not is_ca_bundle_a_transaction_type(processed_event.transaction_type):
            return None
        return CostCalculatorConsumer._complete_bundle_a_reconciliation_key(
            linked_group=(processed_event.linked_transaction_group_id or "").strip(),
            parent_ref=(processed_event.parent_event_reference or "").strip(),
        )

    @staticmethod
    def _complete_bundle_a_reconciliation_key(
        *,
        linked_group: str,
        parent_ref: str,
    ) -> tuple[str, str] | None:
        if linked_group and parent_ref:
            return linked_group, parent_ref
        return None

    @staticmethod
    async def _load_bundle_a_group_events(
        *,
        processed_event: TransactionEvent,
        repo: CostCalculatorRepository,
        linked_group: str,
        parent_ref: str,
    ) -> list[TransactionEvent]:
        group_txns = await repo.get_bundle_a_group_transactions(
            portfolio_id=processed_event.portfolio_id,
            linked_transaction_group_id=linked_group,
            parent_event_reference=parent_ref,
        )
        return [TransactionEvent.model_validate(transaction) for transaction in group_txns]

    @staticmethod
    def _bundle_a_missing_dependencies(
        *,
        processed_event: TransactionEvent,
        group_events: list[TransactionEvent],
    ) -> list[str]:
        available_ids = {event.transaction_id for event in group_events}
        return find_missing_ca_bundle_a_dependencies(processed_event, available_ids)

    @staticmethod
    def _log_bundle_a_reconciliation(
        *,
        processed_event: TransactionEvent,
        linked_group: str,
        parent_ref: str,
        reconciliation: Any,
        missing_dependencies: list[str],
    ) -> None:
        logger.info(
            "bundle_a_reconciliation_state",
            extra={
                "portfolio_id": processed_event.portfolio_id,
                "transaction_id": processed_event.transaction_id,
                "linked_transaction_group_id": linked_group,
                "parent_event_reference": parent_ref,
                "reconciliation_status": reconciliation.status,
                "source_leg_count": reconciliation.source_leg_count,
                "target_leg_count": reconciliation.target_leg_count,
                "cash_consideration_count": reconciliation.cash_consideration_count,
                "source_basis_out_local": str(reconciliation.source_basis_out_local),
                "target_basis_in_local": str(reconciliation.target_basis_in_local),
                "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
                "basis_tolerance": str(reconciliation.basis_tolerance),
                "missing_dependency_reference_ids": missing_dependencies,
            },
        )
        if reconciliation.status == "basis_mismatch":
            logger.warning(
                "bundle_a_basis_mismatch_detected",
                extra={
                    "portfolio_id": processed_event.portfolio_id,
                    "linked_transaction_group_id": linked_group,
                    "parent_event_reference": parent_ref,
                    "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
                    "basis_tolerance": str(reconciliation.basis_tolerance),
                },
            )
        if missing_dependencies:
            logger.warning(
                "bundle_a_dependency_gap_detected",
                extra={
                    "portfolio_id": processed_event.portfolio_id,
                    "transaction_id": processed_event.transaction_id,
                    "linked_transaction_group_id": linked_group,
                    "parent_event_reference": parent_ref,
                    "missing_dependency_reference_ids": missing_dependencies,
                },
            )

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
                payload=publish_event.model_dump(mode="json"),
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

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, PortfolioNotFoundError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        event = None

        try:
            data = json.loads(_message_value(msg))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=data.get("correlation_id"),
            ) as correlation_id:
                event = TransactionEvent.model_validate(data)
                await self._process_valid_cost_event(
                    event=event,
                    event_id=_message_event_id(msg),
                    correlation_id=correlation_id,
                )

        except Exception as exc:
            await self._handle_process_message_error(msg, event, exc)

    async def _process_valid_cost_event(
        self,
        *,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
    ) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                repo = CostCalculatorRepository(db)
                idempotency_repo = IdempotencyRepository(db)
                outbox_repo = OutboxRepository(db)

                if not await idempotency_repo.claim_event_processing(
                    event_id,
                    event.portfolio_id,
                    SERVICE_NAME,
                    correlation_id,
                ):
                    logger.warning("Event already processed. Skipping.")
                    return

                portfolio = await repo.get_portfolio(event.portfolio_id)
                if not portfolio:
                    raise PortfolioNotFoundError(
                        f"Portfolio {event.portfolio_id} not found. Retrying..."
                    )
                instrument = await repo.get_instrument(event.security_id)

                (
                    event,
                    event_transaction_type,
                    cost_basis_method,
                ) = await self._prepare_transaction_event(event, portfolio)
                (
                    events_to_publish,
                    instrument_events_to_publish,
                ) = await self._build_events_to_publish(
                    event=event,
                    event_transaction_type=event_transaction_type,
                    portfolio=portfolio,
                    instrument=instrument,
                    repo=repo,
                    cost_basis_method=cost_basis_method,
                )
                emitted_events = await self._build_emitted_transaction_events(
                    events_to_publish=events_to_publish,
                    repo=repo,
                )
                await self._publish_transaction_events(
                    original_event=event,
                    emitted_events=emitted_events,
                    outbox_repo=outbox_repo,
                    correlation_id=correlation_id,
                )
                await self._publish_instrument_events(
                    instrument_events=instrument_events_to_publish,
                    outbox_repo=outbox_repo,
                    correlation_id=correlation_id,
                )

    async def _handle_process_message_error(
        self,
        msg: Message,
        event: TransactionEvent | None,
        exc: Exception,
    ) -> None:
        if isinstance(exc, (json.JSONDecodeError, ValidationError)):
            logger.error(f"Invalid TransactionEvent; sending to DLQ. Error: {exc}", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
            return
        if isinstance(exc, (FxRateNotFoundError, UpstreamCashLegUnavailableError)):
            self._record_process_message_failure(event, "retryable_error")
            logger.warning(
                "FX dependency not available yet; deferring message without DLQ.", exc_info=True
            )
            raise RetryableConsumerError(str(exc))
        if isinstance(exc, (DBAPIError, IntegrityError, PortfolioNotFoundError)):
            self._record_process_message_failure(event, "retryable_error")
            logger.warning("DB or data availability error; will retry...", exc_info=True)
            raise exc
        self._record_process_message_failure(event, "failed")
        transaction_id = getattr(event, "transaction_id", "UNKNOWN")
        logger.error(
            f"Unexpected error processing transaction {transaction_id}. Sending to DLQ.",
            exc_info=True,
        )
        await self._send_to_dlq_async(msg, exc)

    @staticmethod
    def _record_process_message_failure(event: TransactionEvent | None, status: str) -> None:
        BUY_LIFECYCLE_STAGE_TOTAL.labels("process_message", status).inc()
        if _normalize_event_code(getattr(event, "transaction_type", "")) == "SELL":
            SELL_LIFECYCLE_STAGE_TOTAL.labels("process_message", status).inc()
