"""Resolve authoritative ordering identities before publishing repair commands."""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.transaction_reprocessing import TransactionReprocessingTarget
from ..ports.transaction_reprocessing import TransactionReprocessingTargetReader
from .errors import ValidationRejected


class TransactionReprocessingTargetNotFound(ValidationRejected):
    """Requested transactions are absent from the authoritative Core ledger."""

    def __init__(self, missing_transaction_ids: Sequence[str]) -> None:
        self.missing_transaction_ids = tuple(missing_transaction_ids)
        super().__init__(
            reason_code="INGESTION_REPROCESSING_SOURCE_NOT_FOUND",
            detail={
                "message": "One or more transactions are not available for reprocessing.",
                "missing_transaction_ids": list(self.missing_transaction_ids),
            },
        )


class ResolveTransactionReprocessingTargets:
    """Map transaction ids to source-owned portfolio ordering identities."""

    def __init__(self, reader: TransactionReprocessingTargetReader) -> None:
        self._reader = reader

    async def execute(
        self,
        transaction_ids: Sequence[str],
    ) -> tuple[TransactionReprocessingTarget, ...]:
        ordered_ids = tuple(_normalized_transaction_ids(transaction_ids))
        targets = await self._reader.read_targets(ordered_ids)
        targets_by_id = {target.transaction_id: target for target in targets}
        missing_ids = [
            transaction_id for transaction_id in ordered_ids if transaction_id not in targets_by_id
        ]
        if missing_ids:
            raise TransactionReprocessingTargetNotFound(missing_ids)
        return tuple(targets_by_id[transaction_id] for transaction_id in ordered_ids)


def _normalized_transaction_ids(transaction_ids: Sequence[str]) -> list[str]:
    normalized_ids: list[str] = []
    for transaction_id in transaction_ids:
        if not isinstance(transaction_id, str):
            raise TypeError("transaction_id must be a string")
        normalized = transaction_id.strip()
        if not normalized:
            raise ValueError("transaction_id must not be blank")
        normalized_ids.append(normalized)
    return normalized_ids
