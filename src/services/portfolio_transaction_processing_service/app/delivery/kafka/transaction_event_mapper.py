from __future__ import annotations

from dataclasses import fields
from typing import Any, Iterable

from portfolio_common.events import GOVERNED_EVENT_ENVELOPE_FIELDS, TransactionEvent

from ...application import ProcessTransactionCommand, TransactionEventMetadata
from ...domain import BookedTransaction

_TUPLE_FIELDS = frozenset({"linked_component_ids", "dependency_reference_ids"})
_DOMAIN_FIELD_NAMES = tuple(field.name for field in fields(BookedTransaction))
_DOMAIN_FIELD_SET = frozenset(_DOMAIN_FIELD_NAMES)


class TransactionEventMappingError(ValueError):
    pass


def validate_transaction_event_mapping_contract(
    external_field_names: Iterable[str] | None = None,
) -> None:
    external_fields = set(
        TransactionEvent.model_fields if external_field_names is None else external_field_names
    )
    business_fields = external_fields - GOVERNED_EVENT_ENVELOPE_FIELDS
    missing_domain_fields = sorted(business_fields - _DOMAIN_FIELD_SET)
    extra_domain_fields = sorted(_DOMAIN_FIELD_SET - business_fields)
    if missing_domain_fields or extra_domain_fields:
        raise TransactionEventMappingError(
            "Transaction event/domain field drift: "
            f"missing_domain_fields={missing_domain_fields}, "
            f"extra_domain_fields={extra_domain_fields}"
        )


def map_transaction_event(
    event: TransactionEvent,
    *,
    event_id: str,
    correlation_id: str | None = None,
    traceparent: str | None = None,
) -> ProcessTransactionCommand:
    payload = event.model_dump(mode="python")
    domain_values = {name: payload[name] for name in _DOMAIN_FIELD_NAMES}
    for field_name in _TUPLE_FIELDS:
        value = domain_values[field_name]
        domain_values[field_name] = tuple(value) if value is not None else None
    return ProcessTransactionCommand(
        transaction=BookedTransaction(**domain_values),
        metadata=TransactionEventMetadata(
            event_id=event_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            correlation_id=correlation_id or event.correlation_id,
            traceparent=traceparent or event.traceparent,
        ),
    )


def to_transaction_event(command: ProcessTransactionCommand) -> TransactionEvent:
    payload: dict[str, Any] = {
        name: getattr(command.transaction, name) for name in _DOMAIN_FIELD_NAMES
    }
    payload.update(
        event_type=command.metadata.event_type,
        schema_version=command.metadata.schema_version,
        correlation_id=command.metadata.correlation_id,
        traceparent=command.metadata.traceparent,
    )
    return TransactionEvent.model_validate(payload)


validate_transaction_event_mapping_contract()
