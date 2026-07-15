"""Application use case for effective-dated FX correction revaluation."""

from __future__ import annotations

from ..domain.fx_revaluation import FxRateCorrection, FxRevaluationPlan
from ..ports.fx_revaluation import FxRevaluationRepository, PositionValuationJobWriter


class ProcessFxRateCorrection:
    """Stage durable replay and immediate jobs for one accepted FX correction."""

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
    ) -> FxRevaluationPlan:
        """Persist replay intent before scheduling currently visible position keys."""
        await self._repository.stage_durable_replay(
            correction=correction,
            correlation_id=correlation_id,
        )

        latest_business_date = await self._repository.latest_business_date()
        if latest_business_date is None or correction.effective_date > latest_business_date:
            return FxRevaluationPlan(
                pair=correction.pair,
                effective_date=correction.effective_date,
                immediate_job_count=0,
            )

        position_keys = await self._repository.find_open_position_keys(
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
            )

        return FxRevaluationPlan(
            pair=correction.pair,
            effective_date=correction.effective_date,
            immediate_job_count=len(position_keys),
        )
