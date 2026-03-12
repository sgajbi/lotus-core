# src/services/calculators/cost_calculator_service/app/consumer.py
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, List

from confluent_kafka import Message
from portfolio_common.config import (
    KAFKA_INSTRUMENTS_TOPIC,
    KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
)
from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method
from portfolio_common.db import get_async_db_session
from portfolio_common.events import InstrumentEvent, TransactionEvent
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.monitoring import BUY_LIFECYCLE_STAGE_TOTAL, SELL_LIFECYCLE_STAGE_TOTAL
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.transaction_domain import (
    DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE,
    UPSTREAM_PROVIDED_CASH_ENTRY_MODE,
    assert_ca_bundle_a_transaction_valid,
    assert_fx_processed_event_valid,
    assert_portfolio_flow_cash_entry_mode_allowed,
    assert_upstream_cash_leg_pairing,
    build_auto_generated_adjustment_cash_leg,
    build_fx_contract_instrument_event,
    build_fx_processed_event,
    enrich_dividend_transaction_metadata,
    enrich_fx_transaction_metadata,
    enrich_interest_transaction_metadata,
    enrich_sell_transaction_metadata,
    evaluate_ca_bundle_a_reconciliation,
    find_missing_ca_bundle_a_dependencies,
    is_ca_bundle_a_transaction_type,
    normalize_cash_entry_mode,
    should_auto_generate_cash_leg,
)
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
        normalized_type = (transaction_type or "").upper()
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
        trade_fee_str = event_dict.pop("trade_fee", "0") or "0"
        brokerage = event_dict.pop("brokerage", None)
        stamp_duty = event_dict.pop("stamp_duty", None)
        exchange_fee = event_dict.pop("exchange_fee", None)
        gst = event_dict.pop("gst", None)
        other_fees = event_dict.pop("other_fees", None)

        fee_components = {
            "brokerage": brokerage,
            "stamp_duty": stamp_duty,
            "exchange_fee": exchange_fee,
            "gst": gst,
            "other_fees": other_fees,
        }
        if any(v is not None for v in fee_components.values()):
            normalized = {k: str(Decimal(str(v or "0"))) for k, v in fee_components.items()}
            event_dict["fees"] = normalized
            event_dict["trade_fee"] = str(sum(Decimal(v) for v in normalized.values()))
        elif Decimal(trade_fee_str) > 0:
            event_dict["fees"] = {"brokerage": trade_fee_str}
            event_dict["trade_fee"] = trade_fee_str
        else:
            event_dict["trade_fee"] = "0"

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
        for txn_raw in transactions:
            txn_raw["portfolio_base_currency"] = portfolio_base_currency

            if txn_raw.get("trade_currency") == portfolio_base_currency:
                continue

            fx_rate = await repo.get_fx_rate(
                from_currency=txn_raw["trade_currency"],
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

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, PortfolioNotFoundError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        value = msg.value().decode("utf-8")
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        event = None

        try:
            data = json.loads(value)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=data.get("correlation_id"),
            ):
                correlation_id = correlation_id_var.get()
                event = TransactionEvent.model_validate(data)

                async for db in get_async_db_session():
                    async with db.begin():
                        repo = CostCalculatorRepository(db)
                        idempotency_repo = IdempotencyRepository(db)
                        outbox_repo = OutboxRepository(db)

                        if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                            logger.warning("Event already processed. Skipping.")
                            return

                        portfolio = await repo.get_portfolio(event.portfolio_id)
                        if not portfolio:
                            raise PortfolioNotFoundError(
                                f"Portfolio {event.portfolio_id} not found. Retrying..."
                            )

                    cost_basis_method = normalize_cost_basis_method(portfolio.cost_basis_method)
                    event = enrich_sell_transaction_metadata(
                        event, cost_basis_method=cost_basis_method
                    )
                    event = enrich_fx_transaction_metadata(event)
                    event = enrich_dividend_transaction_metadata(event)
                    event = enrich_interest_transaction_metadata(event)
                    if is_ca_bundle_a_transaction_type(event.transaction_type):
                        assert_ca_bundle_a_transaction_valid(event)

                    event_transaction_type = event.transaction_type.upper()
                    events_to_publish: list[TransactionEvent] = []
                    instrument_events_to_publish: list[InstrumentEvent] = []

                    if event_transaction_type == ADJUSTMENT_TRANSACTION_TYPE:
                        events_to_publish.append(event)
                    elif event_transaction_type in {"FX_SPOT", "FX_FORWARD", "FX_SWAP"}:
                        processed_event = build_fx_processed_event(event)
                        assert_fx_processed_event_valid(processed_event)
                        await repo.create_or_update_transaction_event(processed_event)
                        events_to_publish.append(processed_event)
                        contract_instrument = build_fx_contract_instrument_event(processed_event)
                        if contract_instrument is not None:
                            instrument_events_to_publish.append(contract_instrument)
                    else:
                        history_db = await repo.get_transaction_history(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            exclude_id=event.transaction_id,
                        )

                        history_raw = [
                            self._transform_event_for_engine(TransactionEvent.model_validate(t))
                            for t in history_db
                        ]
                        event_raw = self._transform_event_for_engine(event)

                        all_transactions_raw = await self._enrich_transactions_with_fx(
                            transactions=history_raw + [event_raw],
                            portfolio_base_currency=portfolio.base_currency,
                            repo=repo,
                        )

                        new_transaction_ids = {event.transaction_id}

                        processor = self._get_transaction_processor(cost_basis_method)
                        processed, errored = processor.process_transactions(
                            existing_transactions_raw=[], new_transactions_raw=all_transactions_raw
                        )

                        if errored:
                            new_errors = [
                                e for e in errored if e.transaction_id in new_transaction_ids
                            ]
                            if new_errors:
                                raise ValueError(
                                    f"Transaction engine failed: {new_errors[0].error_reason}"
                                )

                        processed_new = [
                            p for p in processed if p.transaction_id in new_transaction_ids
                        ]

                        for p_txn in processed_new:
                            self._record_lifecycle_stage(
                                p_txn.transaction_type, "persist_transaction_costs", "attempt"
                            )
                            updated_txn = await repo.update_transaction_costs(p_txn)
                            await repo.replace_transaction_cost_breakdown(p_txn)
                            self._record_lifecycle_stage(
                                p_txn.transaction_type, "persist_transaction_costs", "success"
                            )

                            if p_txn.transaction_type == "BUY":
                                self._record_lifecycle_stage(
                                    p_txn.transaction_type, "persist_lot_state", "attempt"
                                )
                                await repo.upsert_buy_lot_state(p_txn)
                                self._record_lifecycle_stage(
                                    p_txn.transaction_type, "persist_lot_state", "success"
                                )
                                self._record_lifecycle_stage(
                                    p_txn.transaction_type,
                                    "persist_accrued_offset_state",
                                    "attempt",
                                )
                                await repo.upsert_accrued_income_offset_state(p_txn)
                                self._record_lifecycle_stage(
                                    p_txn.transaction_type,
                                    "persist_accrued_offset_state",
                                    "success",
                                )
                                logger.info(
                                    "buy_state_persisted",
                                    extra={
                                        "transaction_id": p_txn.transaction_id,
                                        "economic_event_id": getattr(
                                            p_txn, "economic_event_id", None
                                        ),
                                        "linked_transaction_group_id": getattr(
                                            p_txn, "linked_transaction_group_id", None
                                        ),
                                        "calculation_policy_id": getattr(
                                            p_txn, "calculation_policy_id", None
                                        ),
                                        "calculation_policy_version": getattr(
                                            p_txn, "calculation_policy_version", None
                                        ),
                                    },
                                )

                            if p_txn.transaction_type == "SELL":
                                logger.info(
                                    "sell_state_persisted",
                                    extra={
                                        "transaction_id": p_txn.transaction_id,
                                        "economic_event_id": getattr(
                                            p_txn, "economic_event_id", None
                                        ),
                                        "linked_transaction_group_id": getattr(
                                            p_txn, "linked_transaction_group_id", None
                                        ),
                                        "calculation_policy_id": getattr(
                                            p_txn, "calculation_policy_id", None
                                        ),
                                        "calculation_policy_version": getattr(
                                            p_txn, "calculation_policy_version", None
                                        ),
                                    },
                                )

                            if p_txn.fees and p_txn.fees.total_fees > 0:
                                updated_txn.trade_fee = p_txn.fees.total_fees
                            else:
                                updated_txn.trade_fee = Decimal(0)

                            events_to_publish.append(TransactionEvent.model_validate(updated_txn))

                    emitted_events: list[TransactionEvent] = []
                    reconciled_bundle_groups: set[tuple[str, str]] = set()
                    for processed_event in events_to_publish:
                        assert_portfolio_flow_cash_entry_mode_allowed(processed_event)
                        mode = normalize_cash_entry_mode(processed_event.cash_entry_mode)
                        if (
                            processed_event.cash_entry_mode is not None
                            and mode == UPSTREAM_PROVIDED_CASH_ENTRY_MODE
                            and processed_event.transaction_type.upper()
                            != ADJUSTMENT_TRANSACTION_TYPE
                        ):
                            external_cash_id = (
                                processed_event.external_cash_transaction_id or ""
                            ).strip()
                            if not external_cash_id:
                                raise ValueError(
                                    "UPSTREAM_PROVIDED requires "
                                    "external_cash_transaction_id on product leg."
                                )
                            cash_leg_db = await repo.get_transaction_by_id(
                                external_cash_id, portfolio_id=processed_event.portfolio_id
                            )
                            if cash_leg_db is None:
                                raise UpstreamCashLegUnavailableError(
                                    f"Cash leg {external_cash_id} not found for portfolio "
                                    f"{processed_event.portfolio_id}."
                                )
                            cash_leg = TransactionEvent.model_validate(cash_leg_db)
                            assert_upstream_cash_leg_pairing(processed_event, cash_leg)

                        emitted_events.append(processed_event)
                        if should_auto_generate_cash_leg(processed_event):
                            generated_cash_leg = build_auto_generated_adjustment_cash_leg(
                                processed_event
                            )
                            await repo.create_or_update_transaction_event(generated_cash_leg)
                            processed_event.external_cash_transaction_id = (
                                generated_cash_leg.transaction_id
                            )
                            await repo.create_or_update_transaction_event(processed_event)
                            emitted_events.append(generated_cash_leg)

                        if is_ca_bundle_a_transaction_type(processed_event.transaction_type):
                            linked_group = (
                                processed_event.linked_transaction_group_id or ""
                            ).strip()
                            parent_ref = (processed_event.parent_event_reference or "").strip()
                            if linked_group and parent_ref:
                                group_key = (linked_group, parent_ref)
                                if group_key not in reconciled_bundle_groups:
                                    group_txns = await repo.get_bundle_a_group_transactions(
                                        portfolio_id=processed_event.portfolio_id,
                                        linked_transaction_group_id=linked_group,
                                        parent_event_reference=parent_ref,
                                    )
                                    group_events = [
                                        TransactionEvent.model_validate(t) for t in group_txns
                                    ]
                                    reconciliation = evaluate_ca_bundle_a_reconciliation(
                                        group_events,
                                        basis_tolerance=DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE,
                                    )
                                    available_ids = {e.transaction_id for e in group_events}
                                    missing_dependencies = find_missing_ca_bundle_a_dependencies(
                                        processed_event, available_ids
                                    )
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
                                            "cash_consideration_count": (
                                                reconciliation.cash_consideration_count
                                            ),
                                            "source_basis_out_local": str(
                                                reconciliation.source_basis_out_local
                                            ),
                                            "target_basis_in_local": str(
                                                reconciliation.target_basis_in_local
                                            ),
                                            "net_basis_delta_local": str(
                                                reconciliation.net_basis_delta_local
                                            ),
                                            "basis_tolerance": str(reconciliation.basis_tolerance),
                                            "missing_dependency_reference_ids": (
                                                missing_dependencies
                                            ),
                                        },
                                    )
                                    if reconciliation.status == "basis_mismatch":
                                        logger.warning(
                                            "bundle_a_basis_mismatch_detected",
                                            extra={
                                                "portfolio_id": processed_event.portfolio_id,
                                                "linked_transaction_group_id": linked_group,
                                                "parent_event_reference": parent_ref,
                                                "net_basis_delta_local": str(
                                                    reconciliation.net_basis_delta_local
                                                ),
                                                "basis_tolerance": str(
                                                    reconciliation.basis_tolerance
                                                ),
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
                                                "missing_dependency_reference_ids": (
                                                    missing_dependencies
                                                ),
                                            },
                                        )
                                    reconciled_bundle_groups.add(group_key)

                    for publish_event in emitted_events:
                        if event.epoch is not None:
                            publish_event.epoch = event.epoch

                        await outbox_repo.create_outbox_event(
                            aggregate_type="ProcessedTransaction",
                            aggregate_id=str(publish_event.portfolio_id),
                            event_type="ProcessedTransactionPersisted",
                            topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                            payload=publish_event.model_dump(mode="json"),
                            correlation_id=correlation_id,
                        )
                        self._record_lifecycle_stage(
                            publish_event.transaction_type, "emit_outbox", "success"
                        )

                    for instrument_event in instrument_events_to_publish:
                        await outbox_repo.create_outbox_event(
                            aggregate_type="Instrument",
                            aggregate_id=str(instrument_event.security_id),
                            event_type="InstrumentUpserted",
                            topic=KAFKA_INSTRUMENTS_TOPIC,
                            payload=instrument_event.model_dump(mode="json"),
                            correlation_id=correlation_id,
                        )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Invalid TransactionEvent; sending to DLQ. Error: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (FxRateNotFoundError, UpstreamCashLegUnavailableError) as e:
            # Missing FX is a temporal dependency issue. Defer the message so Kafka can redeliver
            # after additional FX events are persisted instead of DLQing the transaction.
            BUY_LIFECYCLE_STAGE_TOTAL.labels("process_message", "retryable_error").inc()
            if getattr(event, "transaction_type", "").upper() == "SELL":
                SELL_LIFECYCLE_STAGE_TOTAL.labels("process_message", "retryable_error").inc()
            logger.warning(
                "FX dependency not available yet; deferring message without DLQ.", exc_info=True
            )
            raise RetryableConsumerError(str(e))
        except (DBAPIError, IntegrityError, PortfolioNotFoundError):
            BUY_LIFECYCLE_STAGE_TOTAL.labels("process_message", "retryable_error").inc()
            if getattr(event, "transaction_type", "").upper() == "SELL":
                SELL_LIFECYCLE_STAGE_TOTAL.labels("process_message", "retryable_error").inc()
            logger.warning("DB or data availability error; will retry...", exc_info=True)
            raise
        except Exception as e:
            BUY_LIFECYCLE_STAGE_TOTAL.labels("process_message", "failed").inc()
            if getattr(event, "transaction_type", "").upper() == "SELL":
                SELL_LIFECYCLE_STAGE_TOTAL.labels("process_message", "failed").inc()
            transaction_id = getattr(event, "transaction_id", "UNKNOWN")
            logger.error(
                f"Unexpected error processing transaction {transaction_id}. Sending to DLQ.",
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, e)
