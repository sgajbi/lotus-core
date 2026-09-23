from datetime import date
from typing import List

from portfolio_common.business_calendar_sql import (
    acquire_default_business_calendar_fallback_lock,
    business_calendar_code_matches,
)
from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    InstrumentReprocessingState,
    PortfolioValuationJob,
)
from portfolio_common.monitoring import (
    observe_valuation_job_lease_transition,
    observe_valuation_worker_jobs_claimed,
    observe_valuation_worker_stale_resets,
)
from portfolio_common.utils import async_timed
from portfolio_common.valuation_repository_base import ValuationRepositoryBase
from sqlalchemy import delete, func, select

from ..domain.source_revaluation import ValuationCalendarClassification


class ValuationRepository(ValuationRepositoryBase):
    """Service-local wrapper preserving valuation orchestrator metrics/import paths."""

    def _observe_jobs_claimed(self, claimed_count: int) -> None:
        observe_valuation_worker_jobs_claimed(claimed_count)

    def _observe_stale_resets(self, reset_count: int) -> None:
        observe_valuation_worker_stale_resets(reset_count)

    def _observe_lease_transition(self, stage: str, outcome: str, count: int) -> None:
        observe_valuation_job_lease_transition(stage, outcome, count)

    @async_timed(repository="ValuationRepository", method="classify_valuation_business_date")
    async def classify_valuation_business_date(
        self, effective_date: date
    ) -> ValuationCalendarClassification:
        """Classify one source date against one atomic calendar/horizon snapshot."""

        classification, calendar_present = await self._read_valuation_business_date(effective_date)
        if calendar_present:
            return classification

        # Concurrent empty-calendar readers share the activation fence, while the first
        # governed calendar writer takes its exclusive counterpart. Re-read after lock
        # acquisition so an activation that won the race cannot be combined with the
        # legacy fallback classification. The caller retains the shared lock through
        # valuation-job staging without serializing unrelated fallback source events.
        await acquire_default_business_calendar_fallback_lock(self.db)
        classification, _ = await self._read_valuation_business_date(effective_date)
        return classification

    async def _read_valuation_business_date(
        self, effective_date: date
    ) -> tuple[ValuationCalendarClassification, bool]:
        """Read membership and every fallback horizon in one database statement."""

        calendar_matches = business_calendar_code_matches(
            BusinessDate.calendar_code, DEFAULT_BUSINESS_CALENDAR_CODE
        )
        calendar_horizon = (
            select(func.max(BusinessDate.date)).where(calendar_matches).scalar_subquery()
        )
        date_exists = (
            select(BusinessDate.date)
            .where(calendar_matches, BusinessDate.date == effective_date)
            .exists()
        )
        snapshot_horizon = select(func.max(DailyPositionSnapshot.date)).scalar_subquery()
        job_horizon = select(func.max(PortfolioValuationJob.valuation_date)).scalar_subquery()
        row = (
            await self.db.execute(
                select(
                    calendar_horizon.label("calendar_horizon"),
                    date_exists.label("is_business_date"),
                    snapshot_horizon.label("snapshot_horizon"),
                    job_horizon.label("job_horizon"),
                )
            )
        ).one()
        if row.calendar_horizon is not None:
            return (
                ValuationCalendarClassification(
                    is_business_date=bool(row.is_business_date),
                    latest_business_date=row.calendar_horizon,
                ),
                True,
            )
        fallback_dates = [
            item for item in (row.snapshot_horizon, row.job_horizon) if item is not None
        ]
        return (
            ValuationCalendarClassification(
                is_business_date=True,
                latest_business_date=max(fallback_dates) if fallback_dates else None,
            ),
            False,
        )

    @async_timed(
        repository="ValuationRepository", method="get_instrument_reprocessing_triggers_count"
    )
    async def get_instrument_reprocessing_triggers_count(self) -> int:
        stmt = select(func.count()).select_from(InstrumentReprocessingState)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    @async_timed(repository="ValuationRepository", method="claim_instrument_reprocessing_triggers")
    async def claim_instrument_reprocessing_triggers(
        self, batch_size: int
    ) -> List[InstrumentReprocessingState]:
        ranked_trigger_ids = (
            select(InstrumentReprocessingState.security_id)
            .order_by(
                InstrumentReprocessingState.earliest_impacted_date.asc(),
                InstrumentReprocessingState.updated_at.asc(),
                InstrumentReprocessingState.security_id.asc(),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        claimed_security_ids = list((await self.db.execute(ranked_trigger_ids)).scalars().all())
        if not claimed_security_ids:
            return []

        stmt = (
            delete(InstrumentReprocessingState)
            .where(InstrumentReprocessingState.security_id.in_(claimed_security_ids))
            .returning(InstrumentReprocessingState)
        )
        result = await self.db.execute(stmt)
        claimed_states = list(result.scalars().all())
        claimed_state_by_security_id = {state.security_id: state for state in claimed_states}
        return [
            claimed_state_by_security_id[security_id]
            for security_id in claimed_security_ids
            if security_id in claimed_state_by_security_id
        ]
