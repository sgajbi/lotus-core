"""Stage calculated cashflow events in the caller-owned outbox transaction."""

from portfolio_common.config import KAFKA_CASHFLOWS_CALCULATED_TOPIC
from portfolio_common.domain.eventing import portfolio_partition_key
from portfolio_common.events import CashflowCalculatedEvent
from portfolio_common.outbox_repository import OutboxRepository

from ...domain import BookedTransaction
from ...domain.cashflow import StoredCashflow


class TransactionalCashflowEventStager:
    """Write calculated-cashflow events to the transactional outbox."""

    def __init__(self, outbox_repository: OutboxRepository) -> None:
        self._outbox_repository = outbox_repository

    async def stage_calculated_cashflow(
        self,
        cashflow: StoredCashflow,
        source_transaction: BookedTransaction,
        *,
        correlation_id: str | None,
    ) -> None:
        event = cashflow_calculated_event(cashflow, source_transaction)
        await self._outbox_repository.create_outbox_event(
            aggregate_type="Cashflow",
            aggregate_id=cashflow.portfolio_id,
            partition_key=portfolio_partition_key(cashflow.portfolio_id),
            event_type="CashflowCalculated",
            topic=KAFKA_CASHFLOWS_CALCULATED_TOPIC,
            payload=event.model_dump(mode="json"),
            correlation_id=correlation_id or "",
        )


def cashflow_calculated_event(
    cashflow: StoredCashflow,
    source_transaction: BookedTransaction,
) -> CashflowCalculatedEvent:
    """Map domain values to the governed calculated-cashflow event contract."""

    return CashflowCalculatedEvent(
        cashflow_id=cashflow.cashflow_id,
        transaction_id=cashflow.transaction_id,
        portfolio_id=cashflow.portfolio_id,
        security_id=cashflow.security_id,
        cashflow_date=cashflow.cashflow_date,
        amount=cashflow.amount,
        currency=cashflow.currency,
        classification=cashflow.classification,
        timing=cashflow.timing,
        is_position_flow=cashflow.is_position_flow,
        is_portfolio_flow=cashflow.is_portfolio_flow,
        calculation_type=cashflow.calculation_type,
        epoch=cashflow.epoch,
        economic_event_id=cashflow.economic_event_id,
        linked_transaction_group_id=cashflow.linked_transaction_group_id,
        parent_event_reference=source_transaction.parent_event_reference,
        linked_cash_transaction_id=source_transaction.linked_cash_transaction_id,
    )
