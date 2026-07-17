"""Application ports for FX correction impact and durable scheduling."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Protocol, Sequence

from portfolio_common.valuation_job_contracts import ValuationJobUpsert

from ..domain.fx_revaluation import (
    DirectCurrencyPair,
    FxRateCorrection,
    PositionValuationKey,
)


class FxRevaluationRepository(Protocol):
    """Resolve FX impact and persist bounded revaluation intent."""

    async def latest_business_date(self) -> date | None:
        """Return the latest governed valuation horizon."""

    async def find_position_keys_requiring_revaluation(
        self,
        *,
        pair: DirectCurrencyPair,
        effective_date: date,
    ) -> Sequence[PositionValuationKey]:
        """Return open epochs whose snapshot predates the persisted direct-pair source."""

    async def find_affected_position_keys(
        self,
        *,
        pair: DirectCurrencyPair,
        earliest_impacted_date: date,
    ) -> Sequence[PositionValuationKey]:
        """Return current epochs held on the date or first opened later."""

    async def stage_durable_replay(
        self,
        *,
        correction: FxRateCorrection,
        correlation_id: str,
    ) -> None:
        """Coalesce durable pair/date replay intent."""


class PositionValuationJobWriter(Protocol):
    """Persist idempotent position valuation jobs."""

    async def upsert_jobs(
        self,
        jobs: Iterable[ValuationJobUpsert],
        *,
        rearm_completed: bool = False,
        requeue_if_processing: bool = False,
    ) -> int:
        """Stage position valuation jobs in the repository's deterministic lock order."""


class PositionWatermarkWriter(Protocol):
    """Reset current position watermarks for bounded replay."""

    async def update_watermarks_if_older(
        self,
        keys: list[tuple[str, str]],
        new_watermark_date: date,
        *,
        touch_if_already_lagging: bool = False,
    ) -> int:
        """Mark affected position keys for replay from the supplied watermark."""


class ReprocessingJobStatusWriter(Protocol):
    """Persist terminal and retry transitions for claimed replay work."""

    async def update_job_status(
        self,
        job_id: int,
        status: str,
        failure_reason: str | None = None,
    ) -> bool:
        """Apply a transition only while the caller retains job ownership."""
