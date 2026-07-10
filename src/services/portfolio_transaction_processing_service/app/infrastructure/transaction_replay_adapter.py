from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from portfolio_common.reprocessing_replay import ReprocessingReplayError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ..application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayInvariantViolation,
)


class CanonicalTransactionReplayer(Protocol):
    async def reprocess_transactions_by_ids(
        self,
        transaction_ids: list[str],
        *,
        correlation_id: str | None = None,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class SqlAlchemyBookedTransactionReplayAdapter:
    session_factory: Callable[[], AsyncSession]
    replayer_factory: Callable[[AsyncSession], CanonicalTransactionReplayer]

    async def replay_booked_transaction(
        self,
        *,
        transaction_id: str,
        correlation_id: str | None,
    ) -> bool:
        try:
            async with self.session_factory() as session:
                replayed_count = await self.replayer_factory(session).reprocess_transactions_by_ids(
                    [transaction_id],
                    correlation_id=correlation_id,
                )
        except (DBAPIError, ReprocessingReplayError) as exc:
            raise BookedTransactionReplayDependencyUnavailable(
                "Canonical booked transaction replay dependency unavailable"
            ) from exc
        if replayed_count not in {0, 1}:
            raise BookedTransactionReplayInvariantViolation(
                "Canonical booked transaction replay must publish zero or one record; "
                f"transaction_id={transaction_id}, replayed_count={replayed_count}"
            )
        return replayed_count == 1
