from __future__ import annotations

from dataclasses import fields

from portfolio_common.events import GOVERNED_EVENT_ENVELOPE_FIELDS, TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository

from src.services.calculators.cost_calculator_service.app.cost_calculation_processor import (
    CostCalculationEventProcessor,
    CostCalculationWorkflow,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
)

from ..domain import BookedTransaction
from ..ports import CostProcessingResult

_DOMAIN_FIELD_NAMES = frozenset(field.name for field in fields(BookedTransaction))
_TUPLE_FIELDS = frozenset({"linked_component_ids", "dependency_reference_ids"})


class CostProcessingCompatibilityAdapter:
    """Run the current cost policy inside the combined caller-owned unit of work."""

    def __init__(
        self,
        *,
        workflow: CostCalculationWorkflow,
        repository: CostCalculatorRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._processor = CostCalculationEventProcessor(workflow)
        self._repository = repository
        self._outbox_repository = outbox_repository

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> CostProcessingResult:
        event = _to_transaction_event(
            transaction,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
        stage_result = await self._processor.stage_valid_event(
            event=event,
            correlation_id=correlation_id or "",
            repo=self._repository,
            outbox_repo=self._outbox_repository,
        )
        return CostProcessingResult(
            processed_transactions=tuple(
                _to_booked_transaction(item) for item in stage_result.emitted_events
            ),
            instrument_update_count=stage_result.instrument_event_count,
        )


def _to_transaction_event(
    transaction: BookedTransaction,
    *,
    correlation_id: str | None,
    traceparent: str | None,
) -> TransactionEvent:
    _validate_mapping_contract()
    payload = {name: getattr(transaction, name) for name in _DOMAIN_FIELD_NAMES}
    payload.update(correlation_id=correlation_id, traceparent=traceparent)
    return TransactionEvent.model_validate(payload)


def _to_booked_transaction(event: TransactionEvent) -> BookedTransaction:
    _validate_mapping_contract()
    payload = event.model_dump(mode="python")
    domain_values = {name: payload[name] for name in _DOMAIN_FIELD_NAMES}
    for field_name in _TUPLE_FIELDS:
        value = domain_values[field_name]
        domain_values[field_name] = tuple(value) if value is not None else None
    return BookedTransaction(**domain_values)


def _validate_mapping_contract() -> None:
    business_fields = set(TransactionEvent.model_fields) - GOVERNED_EVENT_ENVELOPE_FIELDS
    if business_fields != _DOMAIN_FIELD_NAMES:
        raise RuntimeError("TransactionEvent and BookedTransaction fields have drifted")
