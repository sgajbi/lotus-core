"""Event model to persistence record mapping."""

from __future__ import annotations

from typing import Literal

from portfolio_common.events import TransactionEvent, event_business_payload
from pydantic import BaseModel

EventDumpMode = Literal["json", "python"]


def event_business_record_values(
    event: BaseModel,
    *,
    mode: EventDumpMode = "json",
) -> dict[str, object]:
    """Map a validated event model to database-table business values."""
    return event_business_payload(event, mode=mode)


_TRANSACTION_EVENT_ONLY_FIELDS = frozenset(
    {
        "epoch",
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
