from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..ports import (
    BookedTransactionReplayPort,
    TransactionProcessingObserver,
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
)


class BookedTransactionReplayDependencyUnavailable(RuntimeError):
    """Raised when canonical booked-transaction replay cannot reach a dependency."""


class BookedTransactionReplayInvariantViolation(RuntimeError):
    """Raised when replay violates a canonical booked-transaction invariant."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplayBookedTransactionCommand:
    transaction_id: str
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        normalized_transaction_id = self.transaction_id.strip()
        if not normalized_transaction_id:
            raise ValueError("Booked transaction replay requires a transaction_id")
        object.__setattr__(self, "transaction_id", normalized_transaction_id)


class BookedTransactionReplayStatus(StrEnum):
    REPLAYED = "replayed"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplayBookedTransactionResult:
    transaction_id: str
    status: BookedTransactionReplayStatus


class ReplayBookedTransactionUseCase:
    def __init__(
        self,
        replay: BookedTransactionReplayPort,
        observer: TransactionProcessingObserver,
    ) -> None:
        self._replay = replay
        self._observer = observer

    async def execute(
        self,
        command: ReplayBookedTransactionCommand,
    ) -> ReplayBookedTransactionResult:
        with self._observer.observe(TransactionProcessingOperation.REPLAY) as observation:
            replayed = await self._replay.replay_booked_transaction(
                transaction_id=command.transaction_id,
                correlation_id=command.correlation_id,
            )
            status = (
                BookedTransactionReplayStatus.REPLAYED
                if replayed
                else BookedTransactionReplayStatus.NOT_FOUND
            )
            observation.set_outcome(TransactionProcessingOutcome(status.value))
            return ReplayBookedTransactionResult(
                transaction_id=command.transaction_id,
                status=status,
            )
