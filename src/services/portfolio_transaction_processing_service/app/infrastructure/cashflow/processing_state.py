"""Persist cashflow epoch fences and semantic idempotency claims."""

import logging

from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.reprocessing import EpochFencer
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain import BookedTransaction
from ..booked_transaction_event_mapper import to_transaction_event

logger = logging.getLogger(__name__)

CASHFLOW_PROCESSING_SERVICE_NAME = "cashflow-calculator"


class SqlAlchemyCashflowProcessingState:
    """Apply cashflow epoch and semantic-delivery state in the active transaction."""

    def __init__(
        self,
        session: AsyncSession,
        idempotency_repository: IdempotencyRepository,
        *,
        source_topic: str,
    ) -> None:
        self._session = session
        self._idempotency_repository = idempotency_repository
        self._source_topic = source_topic

    async def accepts_epoch(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> bool:
        event = to_transaction_event(
            transaction,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
        return bool(
            await EpochFencer(
                self._session,
                service_name=CASHFLOW_PROCESSING_SERVICE_NAME,
            ).check(event)
        )

    async def claim_semantic_event(
        self,
        transaction: BookedTransaction,
        *,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str | None,
    ) -> bool:
        claimed = bool(
            await self._idempotency_repository.claim_event_processing(
                semantic_event_id,
                transaction.portfolio_id,
                CASHFLOW_PROCESSING_SERVICE_NAME,
                correlation_id or "",
            )
        )
        if not claimed:
            logger.info(
                "Semantic cashflow event already processed; skipping duplicate publication.",
                extra={
                    "transaction_id": transaction.transaction_id,
                    "portfolio_id": transaction.portfolio_id,
                    "epoch": transaction.epoch or 0,
                    "event_id": event_id,
                    "semantic_event_id": semantic_event_id,
                    "topic": self._source_topic,
                },
            )
        return claimed
