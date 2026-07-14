"""Define epoch and semantic-idempotency state required by cashflow processing."""

from typing import Protocol

from ...domain import BookedTransaction


class CashflowProcessingStatePort(Protocol):
    """Fence stale epochs and claim one semantic cashflow effect."""

    async def accepts_epoch(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> bool: ...

    async def claim_semantic_event(
        self,
        transaction: BookedTransaction,
        *,
        event_id: str,
        semantic_event_id: str,
        correlation_id: str | None,
    ) -> bool: ...
