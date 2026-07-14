"""Adapt shared SQLAlchemy position state to immutable application records."""

from __future__ import annotations

from datetime import date
from typing import cast

from portfolio_common.database_models import PositionState
from portfolio_common.position_state_repository import PositionStateRepository

from ...domain.position.history import PositionRecalculationState


class SqlAlchemyPositionRecalculationStateStore:
    """Coordinate dirty windows and epochs without exposing ORM state."""

    def __init__(self, repository: PositionStateRepository) -> None:
        self._repository = repository

    async def get_or_create(
        self, *, portfolio_id: str, security_id: str
    ) -> PositionRecalculationState:
        """Return the current immutable recalculation state for one position key."""
        row = await self._repository.get_or_create_state(portfolio_id, security_id)
        return _to_recalculation_state(row)

    async def advance_epoch(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        expected_epoch: int,
        watermark_date: date,
    ) -> PositionRecalculationState | None:
        """Advance the epoch only while the caller still owns the expected value."""
        row = await self._repository.increment_epoch_and_reset_watermark(
            portfolio_id,
            security_id,
            expected_epoch,
            watermark_date,
        )
        return _to_recalculation_state(row) if row is not None else None

    async def rearm_generation(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        watermark_date: date,
    ) -> bool:
        """Mark downstream generation dirty while preserving the earliest watermark."""
        updated_count = await self._repository.update_watermarks_if_older(
            keys=[(portfolio_id, security_id)],
            new_watermark_date=watermark_date,
            touch_if_already_lagging=True,
        )
        return bool(updated_count)


def _to_recalculation_state(row: PositionState) -> PositionRecalculationState:
    return PositionRecalculationState(
        portfolio_id=str(row.portfolio_id),
        security_id=str(row.security_id),
        epoch=int(row.epoch),
        watermark_date=cast(date, row.watermark_date),
        status=str(row.status),
    )
