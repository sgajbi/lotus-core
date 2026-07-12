from __future__ import annotations

from ..domain import (
    BookedTransaction,
    build_transaction_correction_identity,
    build_transaction_semantic_identity,
)
from ..ports import (
    PositionProcessingResult,
    TransactionIdempotencyOutcome,
    TransactionProcessingObservation,
    TransactionProcessingObserver,
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
    TransactionProcessingUnitOfWorkFactory,
)
from .commands import ProcessTransactionCommand, TransactionProcessingIntent
from .errors import TransactionProcessingRejected
from .results import ProcessTransactionResult, TransactionProcessingStatus


def _cashflow_stage_transactions(
    processed_transactions: tuple[BookedTransaction, ...],
    position_results: list[PositionProcessingResult],
) -> tuple[BookedTransaction, ...]:
    rebuilt_transactions = _rebuilt_position_transactions(position_results)
    if not rebuilt_transactions:
        return processed_transactions

    rebuilt_transaction_keys = {
        (transaction.portfolio_id, transaction.transaction_id)
        for transaction in rebuilt_transactions
    }
    candidates = rebuilt_transactions + tuple(
        transaction
        for transaction in processed_transactions
        if (transaction.portfolio_id, transaction.transaction_id) not in rebuilt_transaction_keys
    )
    seen: set[tuple[str, str, int]] = set()
    unique_transactions = []
    for transaction in candidates:
        key = (
            transaction.portfolio_id,
            transaction.transaction_id,
            transaction.epoch or 0,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_transactions.append(transaction)
    return tuple(unique_transactions)


def _rebuilt_position_transactions(
    position_results: list[PositionProcessingResult],
) -> tuple[BookedTransaction, ...]:
    return tuple(
        transaction
        for position_result in position_results
        for transaction in position_result.cashflow_rebuild_transactions
    )


class ProcessTransactionUseCase:
    def __init__(
        self,
        unit_of_work_factory: TransactionProcessingUnitOfWorkFactory,
        observer: TransactionProcessingObserver,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._observer = observer

    async def execute(self, command: ProcessTransactionCommand) -> ProcessTransactionResult:
        with self._observer.observe(
            TransactionProcessingOperation.TRANSACTION
        ) as transaction_observation:
            try:
                result = await self._execute(command, transaction_observation)
            except TransactionProcessingRejected:
                transaction_observation.set_outcome(TransactionProcessingOutcome.REJECTED)
                raise
            transaction_observation.set_outcome(TransactionProcessingOutcome(result.status.value))
            return result

    async def _execute(
        self,
        command: ProcessTransactionCommand,
        transaction_observation: TransactionProcessingObservation,
    ) -> ProcessTransactionResult:
        transaction = command.transaction
        metadata = command.metadata
        async with self._unit_of_work_factory() as unit_of_work:
            identity = build_transaction_semantic_identity(transaction)
            with self._observer.observe(
                TransactionProcessingOperation.IDEMPOTENCY
            ) as idempotency_observation:
                idempotency_outcome = await unit_of_work.idempotency.claim(
                    event_id=metadata.event_id,
                    portfolio_id=transaction.portfolio_id,
                    semantic_key=identity.semantic_key,
                    payload_fingerprint=identity.payload_fingerprint,
                    correlation_id=metadata.correlation_id,
                )
                correction_claimed = False
                if (
                    idempotency_outcome is TransactionIdempotencyOutcome.SEMANTIC_CONFLICT
                    and metadata.processing_intent is TransactionProcessingIntent.REPAIR
                ):
                    identity = build_transaction_correction_identity(transaction)
                    idempotency_outcome = await unit_of_work.idempotency.claim(
                        event_id=metadata.event_id,
                        portfolio_id=transaction.portfolio_id,
                        semantic_key=identity.semantic_key,
                        payload_fingerprint=identity.payload_fingerprint,
                        correlation_id=metadata.correlation_id,
                    )
                    correction_claimed = (
                        idempotency_outcome is TransactionIdempotencyOutcome.CLAIMED
                    )
                repair_delivery_claimed = (
                    idempotency_outcome is TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE
                    and metadata.processing_intent is TransactionProcessingIntent.REPAIR
                    and await unit_of_work.idempotency.claim_repair_delivery(
                        event_id=metadata.event_id,
                        portfolio_id=transaction.portfolio_id,
                        correlation_id=metadata.correlation_id,
                    )
                )
                if correction_claimed or repair_delivery_claimed:
                    idempotency_observation.set_outcome(TransactionProcessingOutcome.REPLAYED)
                elif idempotency_outcome is not TransactionIdempotencyOutcome.CLAIMED:
                    idempotency_observation.set_outcome(
                        TransactionProcessingOutcome(idempotency_outcome.value)
                    )
            if idempotency_outcome in {
                TransactionIdempotencyOutcome.PHYSICAL_DUPLICATE,
                TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE,
            }:
                if not repair_delivery_claimed:
                    transaction_observation.set_outcome(TransactionProcessingOutcome.DUPLICATE)
                    return ProcessTransactionResult(
                        status=TransactionProcessingStatus.DUPLICATE,
                        input_transaction_id=transaction.transaction_id,
                    )
            if idempotency_outcome is TransactionIdempotencyOutcome.SEMANTIC_CONFLICT:
                raise TransactionProcessingRejected(
                    reason_code="transaction_semantic_conflict",
                    detail={
                        "portfolio_id": transaction.portfolio_id,
                        "transaction_id": transaction.transaction_id,
                        "epoch": transaction.epoch or 0,
                        "semantic_key": identity.semantic_key,
                        "payload_fingerprint": identity.payload_fingerprint,
                    },
                    retryable=False,
                )

            with self._observer.observe(TransactionProcessingOperation.COST):
                cost_result = await unit_of_work.cost.process(
                    transaction,
                    correlation_id=metadata.correlation_id,
                    traceparent=metadata.traceparent,
                )
            position_results = []
            for processed_transaction in cost_result.processed_transactions:
                with self._observer.observe(TransactionProcessingOperation.POSITION):
                    position_results.append(
                        await unit_of_work.position.process(
                            processed_transaction,
                            correlation_id=metadata.correlation_id,
                            traceparent=metadata.traceparent,
                            rebuild_existing=correction_claimed,
                        )
                    )
            rebuilt_transactions = _rebuilt_position_transactions(position_results)
            if rebuilt_transactions:
                with self._observer.observe(TransactionProcessingOperation.PIPELINE):
                    await unit_of_work.pipeline.register_processed_transactions(
                        rebuilt_transactions,
                        correlation_id=metadata.correlation_id,
                        traceparent=metadata.traceparent,
                    )
            cashflow_results = []
            for cashflow_transaction in _cashflow_stage_transactions(
                cost_result.processed_transactions,
                position_results,
            ):
                with self._observer.observe(TransactionProcessingOperation.CASHFLOW):
                    cashflow_results.append(
                        await unit_of_work.cashflow.process(
                            cashflow_transaction,
                            event_id=metadata.event_id,
                            correlation_id=metadata.correlation_id,
                            traceparent=metadata.traceparent,
                            repair_existing=(
                                metadata.processing_intent is TransactionProcessingIntent.REPAIR
                            ),
                        )
                    )
            with self._observer.observe(TransactionProcessingOperation.COMMIT):
                await unit_of_work.commit()

        return ProcessTransactionResult(
            status=TransactionProcessingStatus.PROCESSED,
            input_transaction_id=transaction.transaction_id,
            processed_transaction_ids=tuple(
                item.transaction_id for item in cost_result.processed_transactions
            ),
            instrument_update_count=cost_result.instrument_update_count,
            cashflow_record_count=sum(item.cashflow_record_count for item in cashflow_results),
            position_record_count=sum(item.position_record_count for item in position_results),
            replay_queued_count=sum(item.replay_queued for item in position_results),
        )
