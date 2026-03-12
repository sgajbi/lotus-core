import logging
from datetime import date
from typing import List

from portfolio_common.database_models import (
    InstrumentReprocessingState,
    PositionHistory,
    PositionState,
)
from portfolio_common.monitoring import (
    observe_valuation_worker_jobs_claimed,
    observe_valuation_worker_stale_resets,
)
from portfolio_common.utils import async_timed
from portfolio_common.valuation_repository_base import ValuationRepositoryBase
from sqlalchemy import and_, delete, func, select

logger = logging.getLogger(__name__)


class ValuationRepository(ValuationRepositoryBase):
    """Service-local wrapper preserving valuation orchestrator metrics/import paths."""

    def _observe_jobs_claimed(self, claimed_count: int) -> None:
        observe_valuation_worker_jobs_claimed(claimed_count)

    def _observe_stale_resets(self, reset_count: int) -> None:
        observe_valuation_worker_stale_resets(reset_count)

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
        return list(result.scalars().all())

    @async_timed(
        repository="ValuationRepository", method="find_portfolios_holding_security_on_date"
    )
    async def find_portfolios_holding_security_on_date(
        self, security_id: str, a_date: date
    ) -> List[str]:
        latest_history_subquery = (
            select(
                PositionHistory.portfolio_id,
                PositionHistory.quantity,
                func.row_number()
                .over(
                    partition_by=PositionHistory.portfolio_id,
                    order_by=[PositionHistory.position_date.desc(), PositionHistory.id.desc()],
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == PositionHistory.portfolio_id,
                    PositionState.security_id == PositionHistory.security_id,
                    PositionState.epoch == PositionHistory.epoch,
                ),
            )
            .where(
                PositionHistory.security_id == security_id,
                PositionHistory.position_date <= a_date,
            )
            .subquery()
        )

        stmt = select(latest_history_subquery.c.portfolio_id).where(
            latest_history_subquery.c.rn == 1, latest_history_subquery.c.quantity > 0
        )

        result = await self.db.execute(stmt)
        portfolio_ids = result.scalars().all()
        logger.info(
            "Found %s portfolios holding '%s' on or before %s.",
            len(portfolio_ids),
            security_id,
            a_date,
        )
        return portfolio_ids
