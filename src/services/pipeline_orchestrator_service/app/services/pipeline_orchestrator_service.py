from portfolio_common.events import (
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
    TransactionEvent,
)
from portfolio_common.outbox_repository import OutboxRepository

from ..adapters.pipeline_event_factory import (
    PipelineOutboxMessage,
    financial_reconciliation_requested_message,
    portfolio_day_controls_evaluated_message,
    portfolio_day_ready_for_valuation_message,
    transaction_processing_completed_message,
)
from ..domain.pipeline_stage_state_machine import (
    FINANCIAL_RECONCILIATION_STAGE,
    TRANSACTION_PROCESSING_STAGE,
    decide_transaction_stage_readiness,
    should_emit_control_stage_for_epoch,
    should_register_transaction_stage_for_epoch,
)
from ..domain.pipeline_stage_state_machine import (
    is_control_stage_blocking as is_control_stage_blocking_status,
)
from ..repositories.pipeline_stage_repository import PipelineStageRepository


class PipelineOrchestratorService:
    def __init__(self, repo: PipelineStageRepository, outbox_repo: OutboxRepository):
        self.repo = repo
        self.outbox_repo = outbox_repo

    async def register_processed_transaction(
        self,
        event: TransactionEvent,
        correlation_id: str | None,
    ) -> None:
        event_epoch = event.epoch or 0
        await self.repo.acquire_transaction_stage_lock(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            portfolio_id=event.portfolio_id,
            transaction_id=event.transaction_id,
        )
        latest_epoch = await self.repo.get_latest_transaction_stage_epoch(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            portfolio_id=event.portfolio_id,
            transaction_id=event.transaction_id,
        )
        if not should_register_transaction_stage_for_epoch(
            latest_epoch=latest_epoch,
            event_epoch=event_epoch,
        ):
            return
        stage = await self.repo.upsert_stage_flags(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            transaction_id=event.transaction_id,
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            business_date=event.transaction_date.date(),
            epoch=event_epoch,
            source_event_type="processed_transaction",
            cost_event_seen=True,
            cashflow_event_seen=True,
        )
        await self._emit_if_ready(
            stage,
            correlation_id,
            readiness_reason="atomic_transaction_processing_completed",
        )

    async def register_portfolio_aggregation_completed(
        self,
        event: PortfolioAggregationDayCompletedEvent,
        correlation_id: str | None,
    ) -> None:
        await self._publish_outbox_message(
            financial_reconciliation_requested_message(
                event=event,
                correlation_id=correlation_id,
            ),
            correlation_id=correlation_id,
        )

    async def register_reconciliation_completed(
        self,
        event: FinancialReconciliationCompletedEvent,
        correlation_id: str | None,
    ) -> None:
        stage = await self.repo.upsert_portfolio_control_stage_status(
            stage_name=FINANCIAL_RECONCILIATION_STAGE,
            portfolio_id=event.portfolio_id,
            business_date=event.business_date,
            epoch=event.epoch,
            status=event.outcome_status,
            source_event_type="portfolio_day.reconciliation.completed",
        )
        latest_epoch = await self.repo.get_latest_portfolio_control_stage_epoch(
            stage_name=FINANCIAL_RECONCILIATION_STAGE,
            portfolio_id=event.portfolio_id,
            business_date=event.business_date,
        )
        if not should_emit_control_stage_for_epoch(
            latest_epoch=latest_epoch,
            event_epoch=event.epoch,
        ):
            return
        controls_blocking = is_control_stage_blocking_status(stage.status)
        await self._publish_outbox_message(
            portfolio_day_controls_evaluated_message(
                event=event,
                stage_status=stage.status,
                controls_blocking=controls_blocking,
                correlation_id=correlation_id,
            ),
            correlation_id=correlation_id,
        )

    @staticmethod
    def is_control_stage_blocking(status: str) -> bool:
        return is_control_stage_blocking_status(status)

    async def _emit_if_ready(
        self,
        stage,
        correlation_id: str | None,
        *,
        readiness_reason: str = "atomic_transaction_processing_completed",
    ) -> None:
        readiness_decision = decide_transaction_stage_readiness(stage)
        if not readiness_decision.should_complete:
            return
        if not await self.repo.mark_stage_completed_if_pending(stage):
            return

        await self._publish_outbox_message(
            transaction_processing_completed_message(
                stage=stage,
                readiness_reason=readiness_reason,
                correlation_id=correlation_id,
            ),
            correlation_id=correlation_id,
        )

        readiness_message = portfolio_day_ready_for_valuation_message(
            stage=stage,
            readiness_reason=readiness_reason,
            correlation_id=correlation_id,
        )
        if readiness_message is not None:
            await self._publish_outbox_message(
                readiness_message,
                correlation_id=correlation_id,
            )

    async def _publish_outbox_message(
        self,
        message: PipelineOutboxMessage,
        *,
        correlation_id: str | None,
    ) -> None:
        await self.outbox_repo.create_outbox_event(
            aggregate_type=message.aggregate_type,
            aggregate_id=message.aggregate_id,
            event_type=message.event_type,
            topic=message.topic,
            payload=message.payload,
            correlation_id=correlation_id,
        )
