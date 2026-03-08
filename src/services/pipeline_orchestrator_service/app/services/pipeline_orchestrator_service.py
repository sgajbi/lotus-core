from portfolio_common.config import (
    KAFKA_FINANCIAL_RECONCILIATION_REQUESTED_TOPIC,
    KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC,
)
from portfolio_common.events import (
    CashflowCalculatedEvent,
    FinancialReconciliationRequestedEvent,
    PortfolioAggregationDayCompletedEvent,
    PortfolioDayReadyForValuationEvent,
    TransactionEvent,
    TransactionProcessingCompletedEvent,
)
from portfolio_common.outbox_repository import OutboxRepository

from ..repositories.pipeline_stage_repository import PipelineStageRepository

TRANSACTION_PROCESSING_STAGE = "TRANSACTION_PROCESSING"


class PipelineOrchestratorService:
    def __init__(self, repo: PipelineStageRepository, outbox_repo: OutboxRepository):
        self.repo = repo
        self.outbox_repo = outbox_repo

    async def register_processed_transaction(
        self,
        event: TransactionEvent,
        correlation_id: str | None,
    ) -> None:
        stage = await self.repo.upsert_stage_flags(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            transaction_id=event.transaction_id,
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            business_date=event.transaction_date.date(),
            epoch=event.epoch or 0,
            source_event_type="processed_transaction",
            cost_event_seen=True,
            cashflow_event_seen=False,
        )
        await self._emit_if_ready(stage, correlation_id)

    async def register_cashflow_calculated(
        self, event: CashflowCalculatedEvent, correlation_id: str | None
    ) -> None:
        stage = await self.repo.upsert_stage_flags(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            transaction_id=event.transaction_id,
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            business_date=event.cashflow_date,
            epoch=event.epoch or 0,
            source_event_type="cashflow_calculated",
            cost_event_seen=False,
            cashflow_event_seen=True,
        )
        await self._emit_if_ready(stage, correlation_id)

    async def register_portfolio_aggregation_completed(
        self,
        event: PortfolioAggregationDayCompletedEvent,
        correlation_id: str | None,
    ) -> None:
        reconciliation_event = FinancialReconciliationRequestedEvent(
            portfolio_id=event.portfolio_id,
            business_date=event.aggregation_date,
            epoch=event.epoch,
            correlation_id=correlation_id,
        )
        await self.outbox_repo.create_outbox_event(
            aggregate_type="FinancialReconciliation",
            aggregate_id=f"{event.portfolio_id}:{event.aggregation_date}:{event.epoch}",
            event_type="FinancialReconciliationRequested",
            topic=KAFKA_FINANCIAL_RECONCILIATION_REQUESTED_TOPIC,
            payload=reconciliation_event.model_dump(mode="json"),
            correlation_id=correlation_id,
        )

    async def _emit_if_ready(self, stage, correlation_id: str | None) -> None:
        if stage.status == "COMPLETED":
            return
        if not stage.cost_event_seen or not stage.cashflow_event_seen:
            return
        if not await self.repo.mark_stage_completed_if_pending(stage):
            return

        completion_event = TransactionProcessingCompletedEvent(
            transaction_id=stage.transaction_id,
            portfolio_id=stage.portfolio_id,
            security_id=stage.security_id,
            business_date=stage.business_date,
            epoch=stage.epoch,
            cost_event_seen=True,
            cashflow_event_seen=True,
            correlation_id=correlation_id,
        )
        await self.outbox_repo.create_outbox_event(
            aggregate_type="PipelineStage",
            aggregate_id=f"{stage.portfolio_id}:{stage.transaction_id}:{stage.epoch}",
            event_type="TransactionProcessingCompleted",
            topic=KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC,
            payload=completion_event.model_dump(mode="json"),
            correlation_id=correlation_id,
        )

        if stage.security_id:
            readiness_event = PortfolioDayReadyForValuationEvent(
                portfolio_id=stage.portfolio_id,
                security_id=stage.security_id,
                valuation_date=stage.business_date,
                epoch=stage.epoch,
                correlation_id=correlation_id,
            )
            await self.outbox_repo.create_outbox_event(
                aggregate_type="ValuationReadiness",
                aggregate_id=(
                    f"{stage.portfolio_id}:{stage.security_id}:{stage.business_date}:{stage.epoch}"
                ),
                event_type="PortfolioDayReadyForValuation",
                topic=KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC,
                payload=readiness_event.model_dump(mode="json"),
                correlation_id=correlation_id,
            )
