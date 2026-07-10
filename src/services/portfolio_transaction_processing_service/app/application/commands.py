from __future__ import annotations

from dataclasses import dataclass

from ..domain import BookedTransaction


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionEventMetadata:
    event_id: str
    event_type: str | None = None
    schema_version: str | None = None
    correlation_id: str | None = None
    traceparent: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessTransactionCommand:
    transaction: BookedTransaction
    metadata: TransactionEventMetadata
