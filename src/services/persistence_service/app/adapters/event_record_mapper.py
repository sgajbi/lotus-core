"""Event model to persistence record mapping."""

from __future__ import annotations

from typing import Literal, cast

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.transaction.fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
)
from portfolio_common.events import TransactionEvent, event_business_payload
from pydantic import BaseModel

EventDumpMode = Literal["json", "python"]


def event_business_record_values(
    event: BaseModel,
    *,
    mode: EventDumpMode = "python",
) -> dict[str, object]:
    """Map a validated event model to database-table business values."""
    return cast(dict[str, object], event_business_payload(event, mode=mode))


_TRANSACTION_EVENT_ONLY_FIELDS = frozenset(
    {
        "epoch",
        "tenant_id",
        "brokerage",
        "stamp_duty",
        "exchange_fee",
        "gst",
        "other_fees",
    }
)


def transaction_event_to_record_values(event: TransactionEvent) -> dict[str, object]:
    """Map a validated transaction event to transaction-table values."""
    payload = event_business_record_values(event, mode="python")
    return {
        key: value
        for key, value in payload.items()
        if key not in _TRANSACTION_EVENT_ONLY_FIELDS and value is not None
    }


def transaction_event_fee_component_values(
    event: TransactionEvent,
) -> list[dict[str, object]]:
    """Return positive named fee evidence for atomic raw-ledger persistence."""

    currency = normalize_currency_code(event.trade_currency or event.currency)
    return [
        {
            "transaction_id": event.transaction_id,
            "fee_type": field_name,
            "amount": amount,
            "currency": currency,
        }
        for field_name in TRANSACTION_FEE_COMPONENT_FIELDS
        if (amount := getattr(event, field_name)) is not None and amount > 0
    ]


def transaction_event_has_named_fee_authority(event: TransactionEvent) -> bool:
    """Return whether the event explicitly supplies the named-fee authority surface."""

    return any(
        getattr(event, field_name) is not None for field_name in TRANSACTION_FEE_COMPONENT_FIELDS
    )
