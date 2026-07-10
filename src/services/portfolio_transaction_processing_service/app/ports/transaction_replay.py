from __future__ import annotations

from typing import Protocol


class BookedTransactionReplayPort(Protocol):
    async def replay_booked_transaction(
        self,
        *,
        transaction_id: str,
        correlation_id: str | None,
    ) -> bool: ...
