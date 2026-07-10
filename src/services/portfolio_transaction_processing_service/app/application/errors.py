from __future__ import annotations

from typing import Any


class TransactionProcessingError(Exception):
    """Framework-neutral transaction processing failure."""

    def __init__(
        self,
        *,
        reason_code: str,
        detail: Any,
        retryable: bool,
    ) -> None:
        self.reason_code = reason_code
        self.detail = detail
        self.retryable = retryable
        super().__init__(str(detail))


class TransactionProcessingRejected(TransactionProcessingError):
    """A governed processing fence rejected the transaction."""
