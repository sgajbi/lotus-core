"""Apply shared epoch fencing to canonical booked position commands."""

from __future__ import annotations

from dataclasses import dataclass

from portfolio_common.reprocessing import EpochFencer

from ..domain.booked_transaction import BookedTransaction


@dataclass(frozen=True, slots=True)
class _PositionEpochEnvelope:
    portfolio_id: str
    security_id: str
    epoch: int | None
    topic: str | None = None


class PositionEpochFenceAdapter:
    """Check booked transaction epochs without constructing an event DTO."""

    def __init__(self, fencer: EpochFencer) -> None:
        self._fencer = fencer

    async def is_current(self, transaction: BookedTransaction) -> bool:
        """Return whether the booked transaction belongs to the active epoch."""
        return bool(
            await self._fencer.check(
                _PositionEpochEnvelope(
                    portfolio_id=transaction.portfolio_id,
                    security_id=transaction.security_id,
                    epoch=transaction.epoch,
                )
            )
        )
