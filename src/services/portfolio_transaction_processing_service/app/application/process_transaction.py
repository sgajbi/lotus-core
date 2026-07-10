from __future__ import annotations

from ..ports import TransactionProcessingUnitOfWorkFactory
from .commands import ProcessTransactionCommand
from .results import ProcessTransactionResult, TransactionProcessingStatus


class ProcessTransactionUseCase:
    def __init__(self, unit_of_work_factory: TransactionProcessingUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, command: ProcessTransactionCommand) -> ProcessTransactionResult:
        transaction = command.transaction
        metadata = command.metadata
        async with self._unit_of_work_factory() as unit_of_work:
            claimed = await unit_of_work.idempotency.claim(
                event_id=metadata.event_id,
                portfolio_id=transaction.portfolio_id,
                correlation_id=metadata.correlation_id,
            )
            if not claimed:
                return ProcessTransactionResult(
                    status=TransactionProcessingStatus.DUPLICATE,
                    input_transaction_id=transaction.transaction_id,
                )

            cost_result = await unit_of_work.cost.process(
                transaction,
                correlation_id=metadata.correlation_id,
                traceparent=metadata.traceparent,
            )
            cashflow_result = await unit_of_work.cashflow.process(
                transaction,
                correlation_id=metadata.correlation_id,
                traceparent=metadata.traceparent,
            )
            position_results = [
                await unit_of_work.position.process(
                    processed_transaction,
                    correlation_id=metadata.correlation_id,
                    traceparent=metadata.traceparent,
                )
                for processed_transaction in cost_result.processed_transactions
            ]
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
