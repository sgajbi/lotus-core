"""Application errors mapped to stable Core snapshot HTTP outcomes."""

from __future__ import annotations


class CoreSnapshotBadRequestError(ValueError):
    pass


class CoreSnapshotNotFoundError(ValueError):
    pass


class CoreSnapshotConflictError(ValueError):
    pass


class CoreSnapshotUnavailableSectionError(ValueError):
    pass
