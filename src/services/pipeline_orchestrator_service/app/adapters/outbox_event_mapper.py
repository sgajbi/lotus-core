"""Pipeline event model to outbox payload mapping."""

from __future__ import annotations

from typing import Any

from portfolio_common.event_mapping import outbox_event_payload
from pydantic import BaseModel


def pipeline_outbox_event_payload(event: BaseModel) -> dict[str, Any]:
    """Serialize a governed pipeline event model for outbox persistence."""
    return outbox_event_payload(event)
