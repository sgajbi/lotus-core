import json
import logging

from confluent_kafka import Message
from portfolio_common.config import KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC
from portfolio_common.db import get_async_db_session
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.retry_policy import CONSUMER_DB_EXTENDED_RETRY, tenacity_retry_kwargs
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import retry

from ..cashflow_calculation_workflow import (
    CASHFLOW_COMMIT_OUTCOMES,
    SERVICE_NAME,
    CachedCashflowRule,
    CashflowCalculationWorkflow,
    CashflowProcessingOutcome,
    CashflowStageResult,
    LinkedCashLegError,
    NoCashflowRuleError,
    _cashflow_calculated_event_from_saved_cashflow,
    _log_stale_replay_cashflow_skip,
    _semantic_cashflow_event_id,
)
from ..repositories.cashflow_repository import CashflowRepository

__all__ = [
    "CachedCashflowRule",
    "CashflowCalculationWorkflow",
    "CashflowCalculatorConsumer",
    "CashflowProcessingOutcome",
    "CashflowStageResult",
    "LinkedCashLegError",
    "NoCashflowRuleError",
    "_cashflow_calculated_event_from_saved_cashflow",
]

logger = logging.getLogger(__name__)


def _message_key(msg: Message) -> str:
    return str(msg.key().decode("utf-8")) if msg.key() else "NoKey"


def _message_value(msg: Message) -> str:
    return str(msg.value().decode("utf-8"))


def _message_event_id(msg: Message) -> str:
    return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"


class CashflowCalculatorConsumer(CashflowCalculationWorkflow, BaseConsumer):
    """Compatibility delivery shell retained only while legacy delivery tests are migrated."""

    async def process_message(self, msg: Message):
        await self._process_message_with_retry(msg)

    @retry(
        **tenacity_retry_kwargs(
            profile=CONSUMER_DB_EXTENDED_RETRY,
            retry_exceptions=(IntegrityError,),
            logger=logger,
        )
    )
    async def _process_message_with_retry(self, msg: Message):
        key = _message_key(msg)
        try:
            await self._process_cashflow_event_data(
                msg,
                json.loads(_message_value(msg)),
                _message_event_id(msg),
            )
        except Exception as exc:
            await self._handle_cashflow_processing_error(msg, key, exc)

    async def _process_cashflow_event_data(
        self,
        msg: Message,
        event_data: dict,
        event_id: str,
    ) -> None:
        with self._message_correlation_context(
            msg,
            fallback_correlation_id=event_data.get("correlation_id"),
        ) as correlation_id:
            event = TransactionEvent.model_validate(event_data)
            semantic_event_id = _semantic_cashflow_event_id(event)

            async for db in get_async_db_session():
                await self._process_validated_cashflow_event(
                    db,
                    msg,
                    event,
                    event_id,
                    semantic_event_id,
                    correlation_id,
                )

    async def _handle_cashflow_processing_error(
        self,
        msg: Message,
        key: str,
        exc: Exception,
    ) -> None:
        if isinstance(exc, (json.JSONDecodeError, ValidationError)):
            logger.error("Message validation failed. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid cashflow event payload"))
            return
        if isinstance(exc, IntegrityError):
            logger.warning("DB integrity error; will retry...", exc_info=False)
            raise exc
        if isinstance(exc, NoCashflowRuleError):
            logger.error("Cashflow rule configuration is missing. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, exc)
            return
        if isinstance(exc, LinkedCashLegError):
            logger.error("Linked cash-leg contract is invalid. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, exc)
            return
        logger.error(
            "Unexpected error processing cashflow message with key %s. Sending to DLQ.",
            key,
            exc_info=True,
        )
        await self._send_to_dlq_async(msg, exc)

    async def _process_validated_cashflow_event(
        self,
        db,
        msg: Message,
        event: TransactionEvent,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str,
    ) -> None:
        tx = await db.begin()
        try:
            idempotency_repo = IdempotencyRepository(db)
            cashflow_repo = CashflowRepository(db)
            outbox_repo = OutboxRepository(db)

            outcome = await self._cashflow_processing_outcome(
                db,
                cashflow_repo,
                idempotency_repo,
                outbox_repo,
                event,
                event_id,
                semantic_event_id,
                correlation_id,
                msg.topic(),
            )
            await self._finalize_cashflow_unit_of_work(db=db, tx=tx, outcome=outcome)
        except Exception:
            await tx.rollback()
            raise

    async def _cashflow_processing_outcome(
        self,
        db,
        cashflow_repo: CashflowRepository,
        idempotency_repo: IdempotencyRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str,
        topic: str,
    ) -> CashflowProcessingOutcome:
        physical_replay_outcome = await self._physical_or_stale_replay_outcome(
            cashflow_repo=cashflow_repo,
            idempotency_repo=idempotency_repo,
            event=event,
            event_id=event_id,
            correlation_id=correlation_id,
            topic=topic,
        )
        if physical_replay_outcome is not None:
            return physical_replay_outcome

        fence_outcome = await self._fence_or_semantic_duplicate_outcome(
            db=db,
            idempotency_repo=idempotency_repo,
            event=event,
            event_id=event_id,
            semantic_event_id=semantic_event_id,
            correlation_id=correlation_id,
            topic=topic,
        )
        if fence_outcome is not None:
            return fence_outcome

        stage_result = await self._stage_cashflow_processing(
            db=db,
            cashflow_repo=cashflow_repo,
            outbox_repo=outbox_repo,
            event=event,
            correlation_id=correlation_id,
        )
        return stage_result.outcome

    async def _physical_or_stale_replay_outcome(
        self,
        *,
        cashflow_repo: CashflowRepository,
        idempotency_repo: IdempotencyRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
        topic: str,
    ) -> CashflowProcessingOutcome | None:
        if not await self._claim_physical_event(
            idempotency_repo,
            event,
            event_id,
            correlation_id,
        ):
            return CashflowProcessingOutcome.PHYSICAL_DUPLICATE
        if await self._should_skip_stale_replay_event(cashflow_repo, event, topic):
            return CashflowProcessingOutcome.STALE_REPLAY_SKIPPED
        return None

    @staticmethod
    async def _finalize_cashflow_unit_of_work(
        *, db, tx, outcome: CashflowProcessingOutcome
    ) -> None:
        if outcome in CASHFLOW_COMMIT_OUTCOMES:
            await db.commit()
            return
        await tx.rollback()

    async def _claim_physical_event(
        self,
        idempotency_repo: IdempotencyRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
    ) -> bool:
        claimed = await idempotency_repo.claim_event_processing(
            event_id,
            event.portfolio_id,
            SERVICE_NAME,
            correlation_id,
        )
        if not claimed:
            logger.warning("Cashflow event %s is already processed. Skipping.", event_id)
        return bool(claimed)

    async def _should_skip_stale_replay_event(
        self,
        cashflow_repo: CashflowRepository,
        event: TransactionEvent,
        topic: str,
    ) -> bool:
        if topic != KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC:
            return False
        portfolio_exists = await cashflow_repo.portfolio_exists(event.portfolio_id)
        transaction_exists = await cashflow_repo.transaction_exists(
            event.transaction_id,
            portfolio_id=event.portfolio_id,
        )
        if portfolio_exists and transaction_exists:
            return False
        _log_stale_replay_cashflow_skip(event, topic, portfolio_exists, transaction_exists)
        return True
