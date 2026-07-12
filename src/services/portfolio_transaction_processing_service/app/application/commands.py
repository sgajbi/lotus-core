from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..domain import BookedTransaction


class TransactionProcessingIntent(StrEnum):
    """Declare whether a delivery is normal ingestion or canonical state repair."""

    STANDARD = "standard"
    REPAIR = "repair"


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionEventMetadata:
    event_id: str
    event_type: str | None = None
    schema_version: str | None = None
    correlation_id: str | None = None
    traceparent: str | None = None
    processing_intent: TransactionProcessingIntent = TransactionProcessingIntent.STANDARD


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessTransactionCommand:
    transaction: BookedTransaction
    metadata: TransactionEventMetadata
