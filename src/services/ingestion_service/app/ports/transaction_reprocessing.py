"""Application ports for resolving transaction reprocessing identities."""

from __future__ import annotations

from typing import Protocol, Sequence

from ..domain.transaction_reprocessing import TransactionReprocessingTarget


class TransactionReprocessingTargetReadError(RuntimeError):
    """Raised when authoritative transaction identities cannot be read."""


class TransactionReprocessingTargetReader(Protocol):
    """Read source-owned portfolio identities for transaction repair commands."""

    async def read_targets(
        self,
        *,
        tenant_id: str,
        transaction_ids: Sequence[str],
    ) -> tuple[TransactionReprocessingTarget, ...]: ...
