"""Stage cost-processing domain effects through the governed transactional outbox."""

from collections.abc import Sequence

from portfolio_common.config import (
    KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
    KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
)
from portfolio_common.events import event_business_payload
from portfolio_common.monitoring import BUY_LIFECYCLE_STAGE_TOTAL, SELL_LIFECYCLE_STAGE_TOTAL
from portfolio_common.outbox_repository import OutboxRepository

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import FxContractInstrument
from ..transaction_mapping.booked_transaction import to_transaction_event
from ..transaction_mapping.foreign_exchange_instrument import (
    to_fx_contract_instrument_event,
)


def _normalize_transaction_type(value: object) -> str:
    return str(value or "").strip().upper()


def _record_outbox_lifecycle(transaction_type: object) -> None:
    """Record the existing BUY/SELL transaction outbox lifecycle contract."""

    counter = {
        "BUY": BUY_LIFECYCLE_STAGE_TOTAL,
        "SELL": SELL_LIFECYCLE_STAGE_TOTAL,
    }.get(_normalize_transaction_type(transaction_type))
    if counter is not None:
        counter.labels("emit_outbox", "success").inc()


class TransactionalCostProcessingEffectStager:
    """Map domain effects to integration events in the caller-owned SQL transaction."""

    def __init__(self, outbox_repository: OutboxRepository) -> None:
        self._outbox_repository = outbox_repository

    async def stage_processed_transactions(
        self,
        transactions: Sequence[BookedTransaction],
        *,
        correlation_id: str,
    ) -> None:
        """Stage processed transaction events without publishing outside the unit of work."""

        for transaction in transactions:
            event = to_transaction_event(
                transaction,
                correlation_id=None,
                traceparent=None,
            )
            await self._outbox_repository.create_outbox_event(
                aggregate_type="ProcessedTransaction",
                aggregate_id=str(event.portfolio_id),
                event_type="ProcessedTransactionPersisted",
                topic=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
                payload=event_business_payload(event, mode="json"),
                correlation_id=correlation_id,
            )
            _record_outbox_lifecycle(event.transaction_type)

    async def stage_instrument_updates(
        self,
        instruments: Sequence[FxContractInstrument],
        *,
        correlation_id: str,
    ) -> None:
        """Stage derived instrument updates without leaking event DTOs into application ports."""

        for instrument in instruments:
            event = to_fx_contract_instrument_event(instrument)
            await self._outbox_repository.create_outbox_event(
                aggregate_type="Instrument",
                aggregate_id=str(event.security_id),
                event_type="InstrumentUpserted",
                topic=KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
                payload=event.model_dump(mode="json"),
                correlation_id=correlation_id,
            )
