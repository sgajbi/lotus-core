from dataclasses import dataclass

from portfolio_common.reprocessing_job_repository import (
    ReprocessingJobRepository,
    ResetWatermarksStageOutcome,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .valuation_repository import ValuationRepository


@dataclass(frozen=True)
class InstrumentTriggerConversionResult:
    """Bounded outcome of one trigger-to-durable-job conversion batch."""

    claimed_count: int
    created_count: int
    coalesced_pending_count: int

    def __post_init__(self) -> None:
        if self.claimed_count != self.created_count + self.coalesced_pending_count:
            raise ValueError("Every claimed trigger must have one durable staging outcome.")


class InstrumentReprocessingConversionRepository:
    """Own the atomic trigger-to-job conversion inside the caller's transaction."""

    def __init__(self, db: AsyncSession) -> None:
        self._trigger_repository = ValuationRepository(db)
        self._job_repository = ReprocessingJobRepository(db)

    async def convert_pending_triggers(
        self, *, batch_size: int
    ) -> InstrumentTriggerConversionResult:
        triggers = await self._trigger_repository.claim_instrument_reprocessing_triggers(batch_size)
        created_count = 0
        coalesced_pending_count = 0

        if triggers:
            await self._job_repository.lock_reset_watermarks_replay_identities(
                [trigger.security_id for trigger in triggers]
            )
        for trigger in triggers:
            result = await self._job_repository.stage_reset_watermarks_job(
                security_id=trigger.security_id,
                earliest_impacted_date=trigger.earliest_impacted_date,
                correlation_id=trigger.correlation_id,
            )
            if result.outcome is ResetWatermarksStageOutcome.CREATED:
                created_count += 1
            else:
                coalesced_pending_count += 1

        return InstrumentTriggerConversionResult(
            claimed_count=len(triggers),
            created_count=created_count,
            coalesced_pending_count=coalesced_pending_count,
        )
