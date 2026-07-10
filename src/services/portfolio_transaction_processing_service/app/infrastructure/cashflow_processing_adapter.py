from __future__ import annotations

from typing import Protocol

from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cashflow_calculator_service.app.cashflow_calculation_workflow import (
    CashflowProcessingOutcome,
    CashflowStageResult,
    LinkedCashLegError,
    NoCashflowRuleError,
)
from src.services.calculators.cashflow_calculator_service.app.repositories import (
    cashflow_repository,
)

from ..application import TransactionProcessingError, TransactionProcessingRejected
from ..domain import BookedTransaction
from ..ports import CashflowProcessingResult
from .legacy_transaction_event_mapper import to_transaction_event


class CashflowStagingWorkflow(Protocol):
    async def stage_valid_event(
        self,
        *,
        db: AsyncSession,
        cashflow_repo: cashflow_repository.CashflowRepository,
        idempotency_repo: IdempotencyRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
        topic: str,
    ) -> CashflowStageResult: ...


class CashflowProcessingCompatibilityAdapter:
    """Run current cashflow policy and fences inside the combined unit of work."""

    def __init__(
        self,
        *,
        workflow: CashflowStagingWorkflow,
        db_session: AsyncSession,
        repository: cashflow_repository.CashflowRepository,
        idempotency_repository: IdempotencyRepository,
        outbox_repository: OutboxRepository,
        source_topic: str = KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    ) -> None:
        self._workflow = workflow
        self._db_session = db_session
        self._repository = repository
        self._idempotency_repository = idempotency_repository
        self._outbox_repository = outbox_repository
        self._source_topic = source_topic

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        event_id: str,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> CashflowProcessingResult:
        try:
            stage_result = await self._workflow.stage_valid_event(
                db=self._db_session,
                cashflow_repo=self._repository,
                idempotency_repo=self._idempotency_repository,
                outbox_repo=self._outbox_repository,
                event=to_transaction_event(
                    transaction,
                    correlation_id=correlation_id,
                    traceparent=traceparent,
                ),
                event_id=event_id,
                correlation_id=correlation_id or "",
                topic=self._source_topic,
            )
        except NoCashflowRuleError as exc:
            raise TransactionProcessingError(
                reason_code="cashflow_rule_missing",
                detail={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                    "transaction_type": transaction.transaction_type,
                },
                retryable=False,
            ) from exc
        except LinkedCashLegError as exc:
            raise TransactionProcessingError(
                reason_code="cashflow_contract_invalid",
                detail={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                },
                retryable=False,
            ) from exc
        if stage_result.outcome is CashflowProcessingOutcome.EPOCH_REJECTED:
            raise TransactionProcessingRejected(
                reason_code="cashflow_epoch_rejected",
                detail={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                    "epoch": transaction.epoch,
                },
                retryable=False,
            )
        return CashflowProcessingResult(cashflow_record_count=stage_result.cashflow_record_count)
