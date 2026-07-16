"""PostgreSQL adapter for FX correction impact and durable replay intent."""

from __future__ import annotations

from datetime import date
from typing import cast

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    ReprocessingJob,
)
from portfolio_common.durable_correlation import durable_correlation_diagnostics
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.fx_revaluation import (
    FX_REVALUATION_JOB_TYPE,
    ClaimedFxRevaluationJob,
    DirectCurrencyPair,
    FxRateCorrection,
    PositionValuationKey,
    RejectedFxRevaluationJob,
)
from ...repositories.valuation_repository import ValuationRepository


class SqlAlchemyFxRevaluationRepository:
    """Resolve direct-pair position impact and coalesce durable replay jobs."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._valuation_repository = ValuationRepository(db)

    async def latest_business_date(self) -> date | None:
        """Return the valuation runtime's governed business-date horizon."""
        return cast(date | None, await self._valuation_repository.get_latest_business_date())

    async def claim_pending_jobs(
        self,
        batch_size: int,
    ) -> list[ClaimedFxRevaluationJob | RejectedFxRevaluationJob]:
        """Claim and map the oldest pending FX replay jobs to validated work."""
        claimed_rows = await ReprocessingJobRepository(self._db).find_and_claim_jobs(
            FX_REVALUATION_JOB_TYPE,
            batch_size,
        )
        return [self._map_claimed_job(row) for row in claimed_rows]

    @staticmethod
    def _map_claimed_job(
        row: ReprocessingJob,
    ) -> ClaimedFxRevaluationJob | RejectedFxRevaluationJob:
        """Keep persistence payload parsing inside the infrastructure boundary."""
        try:
            payload = row.payload
            return ClaimedFxRevaluationJob(
                job_id=row.id,
                pair=DirectCurrencyPair(
                    payload["from_currency"],
                    payload["to_currency"],
                ),
                earliest_impacted_date=date.fromisoformat(payload["earliest_impacted_date"]),
                correlation_id=row.correlation_id,
                attempt_count=int(row.attempt_count),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return RejectedFxRevaluationJob(
                job_id=row.id,
                rejection_reason=f"invalid_fx_revaluation_job_payload: {exc}",
                correlation_id=row.correlation_id,
            )

    async def find_open_position_keys(
        self,
        *,
        pair: DirectCurrencyPair,
        effective_date: date,
    ) -> list[PositionValuationKey]:
        """Return current epochs open on date and valued through the exact direct pair."""
        latest_history = _latest_open_position_scope(
            pair=pair,
            effective_date=effective_date,
        )
        statement = _open_position_keys_statement(latest_history)
        rows = (await self._db.execute(statement)).all()
        return [_position_valuation_key(row) for row in rows]

    async def find_position_keys_requiring_revaluation(
        self,
        *,
        pair: DirectCurrencyPair,
        effective_date: date,
    ) -> list[PositionValuationKey]:
        """Return direct-pair keys whose snapshot is absent or older than the source rate."""

        latest_history = _latest_open_position_scope(
            pair=pair,
            effective_date=effective_date,
        )
        statement = (
            _open_position_keys_statement(latest_history)
            .join(
                FxRate,
                (FxRate.from_currency == pair.from_currency)
                & (FxRate.to_currency == pair.to_currency)
                & (FxRate.rate_date == effective_date),
            )
            .outerjoin(
                DailyPositionSnapshot,
                (DailyPositionSnapshot.portfolio_id == latest_history.c.portfolio_id)
                & (DailyPositionSnapshot.security_id == latest_history.c.security_id)
                & (DailyPositionSnapshot.date == effective_date)
                & (DailyPositionSnapshot.epoch == latest_history.c.epoch),
            )
            .where(
                or_(
                    DailyPositionSnapshot.id.is_(None),
                    DailyPositionSnapshot.updated_at < FxRate.updated_at,
                )
            )
        )
        rows = (await self._db.execute(statement)).all()
        return [_position_valuation_key(row) for row in rows]

    async def stage_durable_replay(
        self,
        *,
        correction: FxRateCorrection,
        correlation_id: str,
    ) -> None:
        """Coalesce one pending direct-pair replay job at the earliest affected date."""
        diagnostics = durable_correlation_diagnostics(
            correlation_id=correlation_id,
            record_family="reprocessing_job",
            job_type=FX_REVALUATION_JOB_TYPE,
            currency_pair=correction.pair.key,
            earliest_impacted_date=correction.effective_date,
        )
        await ReprocessingJobRepository(self._db).stage_pending_fx_revaluation_job(
            from_currency=correction.pair.from_currency,
            to_currency=correction.pair.to_currency,
            earliest_impacted_date=correction.effective_date,
            content_hash=correction.content_hash,
            generated_at=correction.generated_at.isoformat(),
            correlation_id=diagnostics.correlation_id,
            correlation_missing_reason=diagnostics.correlation_missing_reason,
            alternate_lookup_key=diagnostics.alternate_lookup_key,
        )

    async def find_affected_position_keys(
        self,
        *,
        pair: DirectCurrencyPair,
        earliest_impacted_date: date,
    ) -> list[PositionValuationKey]:
        """Return direct-pair current epochs held on the date or opened later."""
        open_on_date = await self.find_open_position_keys(
            pair=pair,
            effective_date=earliest_impacted_date,
        )
        future_positions = (
            select(
                PositionHistory.portfolio_id.label("portfolio_id"),
                PositionHistory.security_id.label("security_id"),
                PositionHistory.epoch.label("epoch"),
            )
            .join(
                PositionState,
                (PositionState.portfolio_id == PositionHistory.portfolio_id)
                & (PositionState.security_id == PositionHistory.security_id)
                & (PositionState.epoch == PositionHistory.epoch),
            )
            .join(
                Instrument,
                func.trim(Instrument.security_id) == func.trim(PositionHistory.security_id),
            )
            .join(
                Portfolio,
                func.trim(Portfolio.portfolio_id) == func.trim(PositionHistory.portfolio_id),
            )
            .where(
                PositionHistory.position_date > earliest_impacted_date,
                PositionHistory.quantity > 0,
                func.upper(func.trim(Instrument.currency)) == pair.from_currency,
                func.upper(func.trim(Portfolio.base_currency)) == pair.to_currency,
            )
        )
        future_rows = (await self._db.execute(future_positions.distinct())).all()
        affected = {(key.portfolio_id, key.security_id, key.epoch): key for key in open_on_date}
        for row in future_rows:
            key = PositionValuationKey(row.portfolio_id, row.security_id, row.epoch)
            affected[(key.portfolio_id, key.security_id, key.epoch)] = key
        return [affected[key] for key in sorted(affected)]


def _latest_open_position_scope(*, pair: DirectCurrencyPair, effective_date: date):
    """Build the current-epoch direct-pair position scope for one effective date."""

    return (
        select(
            PositionHistory.portfolio_id.label("portfolio_id"),
            PositionHistory.security_id.label("security_id"),
            PositionHistory.epoch.label("epoch"),
            PositionHistory.quantity.label("quantity"),
            func.row_number()
            .over(
                partition_by=(
                    PositionHistory.portfolio_id,
                    PositionHistory.security_id,
                    PositionHistory.epoch,
                ),
                order_by=(
                    PositionHistory.position_date.desc(),
                    PositionHistory.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .join(
            PositionState,
            (PositionState.portfolio_id == PositionHistory.portfolio_id)
            & (PositionState.security_id == PositionHistory.security_id)
            & (PositionState.epoch == PositionHistory.epoch),
        )
        .join(
            Instrument,
            func.trim(Instrument.security_id) == func.trim(PositionHistory.security_id),
        )
        .join(
            Portfolio,
            func.trim(Portfolio.portfolio_id) == func.trim(PositionHistory.portfolio_id),
        )
        .where(
            PositionHistory.position_date <= effective_date,
            func.upper(func.trim(Instrument.currency)) == pair.from_currency,
            func.upper(func.trim(Portfolio.base_currency)) == pair.to_currency,
        )
        .subquery()
    )


def _open_position_keys_statement(latest_history):
    """Select positive current-epoch keys from one ranked position scope."""

    return (
        select(
            latest_history.c.portfolio_id,
            latest_history.c.security_id,
            latest_history.c.epoch,
        )
        .where(
            latest_history.c.row_number == 1,
            latest_history.c.quantity > 0,
        )
        .order_by(
            latest_history.c.portfolio_id.asc(),
            latest_history.c.security_id.asc(),
            latest_history.c.epoch.asc(),
        )
    )


def _position_valuation_key(row) -> PositionValuationKey:
    """Map one infrastructure query row to the application-facing value object."""

    return PositionValuationKey(
        portfolio_id=row.portfolio_id,
        security_id=row.security_id,
        epoch=row.epoch,
    )
