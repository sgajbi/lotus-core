from __future__ import annotations

from dataclasses import fields

from portfolio_common.events import GOVERNED_EVENT_ENVELOPE_FIELDS, TransactionEvent

from ..domain import BookedTransaction

_DOMAIN_FIELD_NAMES = frozenset(field.name for field in fields(BookedTransaction))
_TUPLE_FIELDS = frozenset({"linked_component_ids", "dependency_reference_ids"})


class LegacyTransactionEventMappingError(RuntimeError):
    pass


def to_transaction_event(
    transaction: BookedTransaction,
    *,
    correlation_id: str | None,
    traceparent: str | None,
) -> TransactionEvent:
    validate_legacy_transaction_event_mapping_contract()
    payload = {name: getattr(transaction, name) for name in _DOMAIN_FIELD_NAMES}
    payload.update(correlation_id=correlation_id, traceparent=traceparent)
    return TransactionEvent.model_validate(payload)


def to_booked_transaction(event: TransactionEvent) -> BookedTransaction:
    validate_legacy_transaction_event_mapping_contract()
    payload = event.model_dump(mode="python")
    domain_values = {name: payload[name] for name in _DOMAIN_FIELD_NAMES}
    for field_name in _TUPLE_FIELDS:
        value = domain_values[field_name]
        domain_values[field_name] = tuple(value) if value is not None else None
    return BookedTransaction(**domain_values)


def validate_legacy_transaction_event_mapping_contract(
    external_field_names: set[str] | None = None,
) -> None:
    external_fields = (
        set(TransactionEvent.model_fields) if external_field_names is None else external_field_names
    )
    business_fields = external_fields - GOVERNED_EVENT_ENVELOPE_FIELDS
    missing_domain_fields = sorted(business_fields - _DOMAIN_FIELD_NAMES)
    extra_domain_fields = sorted(_DOMAIN_FIELD_NAMES - business_fields)
    if missing_domain_fields or extra_domain_fields:
        raise LegacyTransactionEventMappingError(
            "Transaction event/domain field drift: "
            f"missing_domain_fields={missing_domain_fields}, "
            f"extra_domain_fields={extra_domain_fields}"
        )
