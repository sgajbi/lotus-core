from __future__ import annotations

from typing import Protocol

from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from ..application import (
    TransactionProcessingError,
    TransactionProcessingRejected,
    build_settlement_cash_rejection,
)
from ..domain import BookedTransaction
from ..domain.cashflow import CashflowCalculationContext
from ..domain.transaction import SettlementCashValidationError
from ..ports import CashflowProcessingResult
from .booked_transaction_event_mapper import to_transaction_event
from .cashflow.persistence import SqlAlchemyCashflowRepository
from .cashflow_staging_workflow import (
    CashflowProcessingOutcome,
    CashflowStageResult,
    LinkedCashLegError,
    NoCashflowRuleError,
)


class CashflowStagingWorkflow(Protocol):
    async def stage_valid_event(
        self,
        *,
        db: AsyncSession,
        cashflow_repo: SqlAlchemyCashflowRepository,
        idempotency_repo: IdempotencyRepository,
        outbox_repo: OutboxRepository,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
        topic: str,
        repair_existing: bool = False,
        booked_transaction: BookedTransaction | None = None,
        calculation_context: CashflowCalculationContext = (
            CashflowCalculationContext.CURRENT_BOOKING
        ),
    ) -> CashflowStageResult: ...


class CashflowProcessingCompatibilityAdapter:
    """Run current cashflow policy and fences inside the combined unit of work."""

    def __init__(
        self,
        *,
        workflow: CashflowStagingWorkflow,
        db_session: AsyncSession,
        repository: SqlAlchemyCashflowRepository,
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
        repair_existing: bool = False,
        calculation_context: CashflowCalculationContext = (
            CashflowCalculationContext.CURRENT_BOOKING
        ),
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
                repair_existing=repair_existing,
                booked_transaction=transaction,
                calculation_context=calculation_context,
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
        except SettlementCashValidationError as exc:
            raise build_settlement_cash_rejection(transaction, exc) from exc
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
