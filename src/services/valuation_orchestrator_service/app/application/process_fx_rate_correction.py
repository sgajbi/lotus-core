"""Application use case for effective-dated FX correction revaluation."""

from __future__ import annotations

from ..domain.fx_revaluation import FxRateCorrection, FxRevaluationPlan
from ..domain.source_revaluation import decide_source_revaluation_schedule
from ..ports.fx_revaluation import FxRevaluationRepository, PositionValuationJobWriter


class ProcessFxRateCorrection:
    """Schedule the minimum correct work for one accepted FX correction."""

    def __init__(
        self,
        *,
        repository: FxRevaluationRepository,
        valuation_jobs: PositionValuationJobWriter,
    ) -> None:
        self._repository = repository
        self._valuation_jobs = valuation_jobs

    async def execute(
        self,
        *,
        correction: FxRateCorrection,
        correlation_id: str,
        source_correction_id: str,
    ) -> FxRevaluationPlan:
        """Schedule visible positions and preserve replay only when timing requires it."""
        latest_business_date = await self._repository.latest_business_date()
        schedule = decide_source_revaluation_schedule(
            effective_date=correction.effective_date,
            latest_business_date=latest_business_date,
        )

        if schedule.stage_durable_replay:
            await self._repository.stage_durable_replay(
                correction=correction,
                correlation_id=correlation_id,
            )

        if not schedule.scan_visible_positions:
            return FxRevaluationPlan(
                pair=correction.pair,
                effective_date=correction.effective_date,
                immediate_job_count=0,
                durable_replay_staged=schedule.stage_durable_replay,
            )

        position_keys = await self._repository.find_position_keys_requiring_revaluation(
            pair=correction.pair,
            effective_date=correction.effective_date,
        )
        for key in position_keys:
            await self._valuation_jobs.upsert_job(
                portfolio_id=key.portfolio_id,
                security_id=key.security_id,
                valuation_date=correction.effective_date,
                epoch=key.epoch,
                correlation_id=correlation_id,
                source_correction_id=source_correction_id,
                rearm_completed=True,
                requeue_if_processing=True,
            )

        return FxRevaluationPlan(
            pair=correction.pair,
            effective_date=correction.effective_date,
            immediate_job_count=len(position_keys),
            durable_replay_staged=schedule.stage_durable_replay,
        )
