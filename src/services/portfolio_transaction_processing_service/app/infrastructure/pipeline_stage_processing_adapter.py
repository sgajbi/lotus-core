"""Publish transaction-owned stage readiness through the transactional outbox."""

from __future__ import annotations

from portfolio_common.config import (
    KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
)
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import (
    PortfolioDayReadyForValuationEvent,
    TransactionProcessingCompletedEvent,
)
from portfolio_common.outbox_repository import OutboxRepository

from ..domain import BookedTransaction
from .transaction_stage_repository import SqlAlchemyTransactionStageRepository

TRANSACTION_PROCESSING_STAGE = "TRANSACTION_PROCESSING"
_READINESS_REASON = "atomic_transaction_processing_completed"


class PipelineStageProcessingAdapter:
    """Register processed transactions and emit each newly completed stage once."""

    def __init__(
        self,
        repository: SqlAlchemyTransactionStageRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._repository = repository
        self._outbox_repository = outbox_repository

    async def register_processed_transactions(
        self,
        transactions: tuple[BookedTransaction, ...],
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None:
        for transaction in transactions:
            await self._register_processed_transaction(
                transaction,
                correlation_id=correlation_id,
            )

    async def _register_processed_transaction(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
    ) -> None:
        event_epoch = transaction.epoch or 0
        await self._repository.acquire_stage_lock(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            portfolio_id=transaction.portfolio_id,
            transaction_id=transaction.transaction_id,
        )
        latest_epoch = await self._repository.latest_epoch(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            portfolio_id=transaction.portfolio_id,
            transaction_id=transaction.transaction_id,
        )
        if latest_epoch is not None and event_epoch < latest_epoch:
            return

        stage = await self._repository.upsert_processed_stage(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            business_date=transaction.transaction_date.date(),
            epoch=event_epoch,
        )
        if stage.status == "COMPLETED" or not stage.cost_event_seen:
            return
        if not await self._repository.claim_completion(stage):
            return

        completed_event = TransactionProcessingCompletedEvent(
            transaction_id=stage.transaction_id,
            portfolio_id=stage.portfolio_id,
            security_id=stage.security_id,
            business_date=stage.business_date,
            epoch=stage.epoch,
            cost_event_seen=True,
            cashflow_event_seen=True,
            readiness_reason=_READINESS_REASON,
            correlation_id=correlation_id,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="PipelineStage",
            aggregate_id=f"{stage.portfolio_id}:{stage.transaction_id}:{stage.epoch}",
            event_type="TransactionProcessingCompleted",
            topic=KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
            payload=outbox_event_payload(completed_event),
            correlation_id=correlation_id,
        )

        if not stage.security_id:
            return
        valuation_event = PortfolioDayReadyForValuationEvent(
            portfolio_id=stage.portfolio_id,
            security_id=stage.security_id,
            valuation_date=stage.business_date,
            epoch=stage.epoch,
            readiness_reason=_READINESS_REASON,
            correlation_id=correlation_id,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="ValuationReadiness",
            aggregate_id=(
                f"{stage.portfolio_id}:{stage.security_id}:{stage.business_date}:{stage.epoch}"
            ),
            event_type="PortfolioDayReadyForValuation",
            topic=KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
            payload=outbox_event_payload(valuation_event),
            correlation_id=correlation_id,
        )
