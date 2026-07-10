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
    PIPELINE = "pipeline"
    COMMIT = "commit"
    REPLAY = "replay"


class TransactionProcessingOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    PHYSICAL_DUPLICATE = "physical_duplicate"
    SEMANTIC_DUPLICATE = "semantic_duplicate"
    SEMANTIC_CONFLICT = "semantic_conflict"
    REPLAYED = "replayed"
    NOT_FOUND = "not_found"
    REJECTED = "rejected"
    FAILED = "failed"


class TransactionProcessingObservation(Protocol):
    def set_outcome(self, outcome: TransactionProcessingOutcome) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None: ...


class TransactionProcessingObserver(Protocol):
    def observe(
        self,
        operation: TransactionProcessingOperation,
    ) -> AbstractContextManager[TransactionProcessingObservation]: ...
