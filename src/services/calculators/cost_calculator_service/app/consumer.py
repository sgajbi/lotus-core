# src/services/calculators/cost_calculator_service/app/consumer.py
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, List

from confluent_kafka import Message
from engine.transaction_processor import TransactionProcessor
from logic.cost_basis_strategies import AverageCostBasisStrategy, FIFOBasisStrategy
from logic.cost_calculator import CostCalculator
from logic.disposition_engine import DispositionEngine
from logic.error_reporter import ErrorReporter
from logic.parser import TransactionParser
from logic.sorter import TransactionSorter
from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.db import get_async_db_session
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.monitoring import BUY_LIFECYCLE_STAGE_TOTAL, SELL_LIFECYCLE_STAGE_TOTAL
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.transaction_domain import enrich_sell_transaction_metadata
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .repository import CostCalculatorRepository

logger = logging.getLogger(__name__)
SERVICE_NAME = "cost-calculator"


class FxRateNotFoundError(Exception):
    """Raised when a required FX rate is not yet available in the database."""

    pass


class PortfolioNotFoundError(Exception):
    """Raised when the portfolio for a transaction is not yet in the database."""

    pass


class CostCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction events, calculates costs/realized P&L,
    persists updates, and emits a full TransactionEvent downstream.
    """

    def _get_transaction_processor(self, cost_basis_method: str = "FIFO") -> TransactionProcessor:
        """
        Builds and returns an instance of the TransactionProcessor, injecting
        the specified cost basis strategy.
        """
        error_reporter = ErrorReporter()
        parser = TransactionParser(error_reporter=error_reporter)
        sorter = TransactionSorter()

        if cost_basis_method == "AVCO":
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
        financial-calculator-engine, converting fee fields to a Fees object structure.
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
            normalized = {
                k: str(Decimal(str(v or "0")))
                for k, v in fee_components.items()
            }
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
        correlation_id = correlation_id_var.get()
        event = None

        try:
            data = json.loads(value)
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

                    cost_basis_method = portfolio.cost_basis_method or "FIFO"
                    event = enrich_sell_transaction_metadata(
                        event, cost_basis_method=cost_basis_method
                    )

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
                        new_errors = [e for e in errored if e.transaction_id in new_transaction_ids]
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
                                p_txn.transaction_type, "persist_accrued_offset_state", "attempt"
                            )
                            await repo.upsert_accrued_income_offset_state(p_txn)
                            self._record_lifecycle_stage(
                                p_txn.transaction_type, "persist_accrued_offset_state", "success"
                            )
                            logger.info(
                                "buy_state_persisted",
                                extra={
                                    "transaction_id": p_txn.transaction_id,
                                    "economic_event_id": getattr(p_txn, "economic_event_id", None),
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
                                    "economic_event_id": getattr(p_txn, "economic_event_id", None),
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

                        full_event_to_publish = TransactionEvent.model_validate(updated_txn)

                        if event.epoch is not None:
                            full_event_to_publish.epoch = event.epoch

                        await outbox_repo.create_outbox_event(
                            aggregate_type="ProcessedTransaction",
                            aggregate_id=str(p_txn.portfolio_id),
                            event_type="ProcessedTransactionPersisted",
                            topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                            payload=full_event_to_publish.model_dump(mode="json"),
                            correlation_id=correlation_id,
                        )
                        self._record_lifecycle_stage(
                            p_txn.transaction_type, "emit_outbox", "success"
                        )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Invalid TransactionEvent; sending to DLQ. Error: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except FxRateNotFoundError as e:
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
