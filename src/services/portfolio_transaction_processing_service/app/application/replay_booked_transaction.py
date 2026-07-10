from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..ports import BookedTransactionReplayPort


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
    def __init__(self, replay: BookedTransactionReplayPort) -> None:
        self._replay = replay

    async def execute(
        self,
        command: ReplayBookedTransactionCommand,
    ) -> ReplayBookedTransactionResult:
        replayed = await self._replay.replay_booked_transaction(
            transaction_id=command.transaction_id,
            correlation_id=command.correlation_id,
        )
        return ReplayBookedTransactionResult(
            transaction_id=command.transaction_id,
            status=(
                BookedTransactionReplayStatus.REPLAYED
                if replayed
                else BookedTransactionReplayStatus.NOT_FOUND
            ),
        )
