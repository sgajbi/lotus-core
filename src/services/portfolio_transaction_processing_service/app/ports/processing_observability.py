from __future__ import annotations

from contextlib import AbstractContextManager
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self


class TransactionProcessingOperation(StrEnum):
    TRANSACTION = "transaction"
    IDEMPOTENCY = "idempotency"
    COST = "cost"
    CASHFLOW = "cashflow"
    POSITION = "position"
    COMMIT = "commit"
    REPLAY = "replay"


class TransactionProcessingOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    REPLAYED = "replayed"
    NOT_FOUND = "not_found"
    REJECTED = "rejected"
    FAILED = "failed"


class TransactionProcessingObservation(Protocol):
    def set_outcome(self, outcome: TransactionProcessingOutcome) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class TransactionProcessingObserver(Protocol):
    def observe(
        self,
        operation: TransactionProcessingOperation,
    ) -> AbstractContextManager[TransactionProcessingObservation]: ...
