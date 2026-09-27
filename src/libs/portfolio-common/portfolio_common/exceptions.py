# src/libs/portfolio-common/portfolio_common/exceptions.py


from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TransactionSemanticConflictError(ValueError):
    """Reject a materially changed replay of an immutable source transaction."""

    semantic_key: str
    incoming_payload_fingerprint: str
    existing_payload_fingerprint: str | None = None
    reason_code: str = "TRANSACTION_SEMANTIC_CONFLICT"

    def __str__(self) -> str:
        existing = self.existing_payload_fingerprint or "unavailable"
        return (
            f"{self.reason_code}: existing_payload_fingerprint={existing}; "
            f"incoming_payload_fingerprint={self.incoming_payload_fingerprint}"
        )


class RetryableConsumerError(Exception):
    """
    Custom exception raised by a consumer when a transient, recoverable error
    occurs (e.g., temporary database outage).

    The BaseConsumer catches this exception, preserves partition order, and
    retries the same message in-process after the governed backoff. The offset
    remains uncommitted until processing succeeds or the configured retry
    budget routes the message through terminal recovery.
    """

    pass
