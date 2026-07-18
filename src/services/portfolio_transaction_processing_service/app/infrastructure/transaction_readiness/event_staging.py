"""Stage transaction and valuation readiness through the transactional outbox."""

from __future__ import annotations

from portfolio_common.config import (
    KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
)
from portfolio_common.domain.eventing import (
    portfolio_partition_key,
    portfolio_security_partition_key,
)
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import (
    PortfolioDayReadyForValuationEvent,
    TransactionProcessingCompletedEvent,
)
from portfolio_common.outbox_repository import OutboxRepository

from ...domain import TransactionStageRecord

_READINESS_REASON = "atomic_transaction_processing_completed"


class TransactionalTransactionReadinessEventStager:
    """Map claimed readiness state to governed outbox events."""

    def __init__(self, outbox_repository: OutboxRepository) -> None:
        self._outbox_repository = outbox_repository

    async def stage_transaction_readiness(
        self,
        stage: TransactionStageRecord,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None:
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
            traceparent=traceparent,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="PipelineStage",
            aggregate_id=f"{stage.portfolio_id}:{stage.transaction_id}:{stage.epoch}",
            partition_key=portfolio_partition_key(stage.portfolio_id),
            event_type="TransactionProcessingCompleted",
            topic=KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
            payload=outbox_event_payload(completed_event),
            correlation_id=correlation_id,
            traceparent=traceparent,
        )

        if not stage.security_id:
            return
        valuation_event = PortfolioDayReadyForValuationEvent(
            portfolio_id=stage.portfolio_id,
            security_id=stage.security_id,
            valuation_date=stage.business_date,
            epoch=stage.epoch,
            source_transaction_id=stage.transaction_id,
            readiness_reason=_READINESS_REASON,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="ValuationReadiness",
            aggregate_id=(
                f"{stage.portfolio_id}:{stage.security_id}:{stage.business_date}:{stage.epoch}"
            ),
            partition_key=portfolio_security_partition_key(
                stage.portfolio_id,
                stage.security_id,
            ),
            event_type="PortfolioDayReadyForValuation",
            topic=KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
            payload=outbox_event_payload(valuation_event),
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
