"""Ports for transaction-owned processing and valuation readiness."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from ..domain import TransactionStageRecord


class TransactionReadinessRepository(Protocol):
    """Persist and epoch-fence transaction processing readiness state."""

    async def acquire_stage_lock(
        self,
        *,
        stage_name: str,
        portfolio_id: str,
        transaction_id: str,
    ) -> None: ...

    async def latest_epoch(
        self,
        *,
        stage_name: str,
        portfolio_id: str,
        transaction_id: str,
    ) -> int | None: ...

    async def upsert_processed_stage(
        self,
        *,
        stage_name: str,
        transaction_id: str,
        portfolio_id: str,
        security_id: str | None,
        business_date: date,
        epoch: int,
    ) -> TransactionStageRecord: ...

    async def claim_completion(self, stage: TransactionStageRecord) -> bool: ...


class TransactionReadinessEventStagingPort(Protocol):
    """Stage governed readiness facts in the caller-owned transaction."""

    async def stage_transaction_readiness(
        self,
        stage: TransactionStageRecord,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None: ...
