"""Application errors raised while materializing position timeseries."""


class PositionSnapshotTriggerMismatch(RuntimeError):
    """Reject a trigger whose identity differs from its authoritative snapshot."""
