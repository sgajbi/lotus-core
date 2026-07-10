from __future__ import annotations

from ..ports import (
    TransactionProcessingObservation,
    TransactionProcessingObserver,
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
    TransactionProcessingUnitOfWorkFactory,
)
from .commands import ProcessTransactionCommand
from .errors import TransactionProcessingRejected
from .results import ProcessTransactionResult, TransactionProcessingStatus


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
            with self._observer.observe(TransactionProcessingOperation.IDEMPOTENCY):
                claimed = await unit_of_work.idempotency.claim(
                    event_id=metadata.event_id,
                    portfolio_id=transaction.portfolio_id,
                    correlation_id=metadata.correlation_id,
                )
            if not claimed:
                transaction_observation.set_outcome(TransactionProcessingOutcome.DUPLICATE)
                return ProcessTransactionResult(
                    status=TransactionProcessingStatus.DUPLICATE,
                    input_transaction_id=transaction.transaction_id,
                )

            with self._observer.observe(TransactionProcessingOperation.COST):
                cost_result = await unit_of_work.cost.process(
                    transaction,
                    correlation_id=metadata.correlation_id,
                    traceparent=metadata.traceparent,
                )
            with self._observer.observe(TransactionProcessingOperation.CASHFLOW):
                cashflow_result = await unit_of_work.cashflow.process(
                    transaction,
                    event_id=metadata.event_id,
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
            cashflow_record_count=cashflow_result.cashflow_record_count,
            position_record_count=sum(item.position_record_count for item in position_results),
            replay_queued_count=sum(item.replay_queued for item in position_results),
        )
