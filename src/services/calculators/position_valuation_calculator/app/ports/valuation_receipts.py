"""Application boundary for durable position valuation receipts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from portfolio_common.domain.valuation import ValuationCalculationReceipt


class ValuationReceiptRepository(Protocol):
    """Persist and reconstruct one receipt per position snapshot."""

    async def upsert(
        self,
        *,
        snapshot_id: int,
        receipt: ValuationCalculationReceipt,
    ) -> ValuationCalculationReceipt: ...

    async def fetch_many(
        self,
        snapshot_ids: Sequence[int],
    ) -> Mapping[int, ValuationCalculationReceipt]: ...
