"""Governed lifecycle states for position calculation authority."""

from enum import StrEnum


class PositionStateStatus(StrEnum):
    """Durable posture of a portfolio/security position calculation key."""

    CURRENT = "CURRENT"
    REPROCESSING = "REPROCESSING"
    SNAPSHOT_ONLY = "SNAPSHOT_ONLY"


SCHEDULABLE_POSITION_STATE_STATUSES = (
    PositionStateStatus.CURRENT,
    PositionStateStatus.REPROCESSING,
)


__all__ = ["PositionStateStatus", "SCHEDULABLE_POSITION_STATE_STATUSES"]
