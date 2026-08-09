"""Register completed transaction processing with monotonic epoch semantics."""

from __future__ import annotations

from ...domain import BookedTransaction
from ...ports.transaction_readiness import (
    TransactionReadinessEventStagingPort,
    TransactionReadinessRepository,
)

TRANSACTION_PROCESSING_STAGE = "TRANSACTION_PROCESSING"


class RegisterTransactionReadinessUseCase:
    """Claim and stage each newly completed transaction-processing fact once."""

    def __init__(
        self,
        *,
        repository: TransactionReadinessRepository,
        events: TransactionReadinessEventStagingPort,
    ) -> None:
        self._repository = repository
        self._events = events

    async def register_processed_transactions(
        self,
        transactions: tuple[BookedTransaction, ...],
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None:
        """Register a batch in deterministic input order within one transaction."""

        for transaction in transactions:
            await self._register_processed_transaction(
                transaction,
                correlation_id=correlation_id,
                traceparent=traceparent,
            )

    async def _register_processed_transaction(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None:
        event_epoch = transaction.epoch or 0
        await self._repository.acquire_stage_lock(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            portfolio_id=transaction.portfolio_id,
            transaction_id=transaction.transaction_id,
        )
        stage = await self._repository.claim_processed_stage(
            stage_name=TRANSACTION_PROCESSING_STAGE,
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            business_date=transaction.transaction_date.date(),
            epoch=event_epoch,
        )
        if stage is None:
            return

        await self._events.stage_transaction_readiness(
            stage,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
