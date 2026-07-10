from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TransactionProcessingStatus(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessTransactionResult:
    status: TransactionProcessingStatus
    input_transaction_id: str
    processed_transaction_ids: tuple[str, ...] = ()
    instrument_update_count: int = 0
    cashflow_record_count: int = 0
    position_record_count: int = 0
    replay_queued_count: int = 0
