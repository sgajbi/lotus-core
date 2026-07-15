"""PostgreSQL adapter for FX correction impact and durable replay intent."""

from __future__ import annotations

from datetime import date
from typing import cast

from portfolio_common.database_models import (
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    ReprocessingJob,
)
from portfolio_common.durable_correlation import durable_correlation_diagnostics
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import Date, String, bindparam, func, select, text
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
        latest_history = (
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
        statement = (
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
        rows = (await self._db.execute(statement)).all()
        return [
            PositionValuationKey(
                portfolio_id=row.portfolio_id,
                security_id=row.security_id,
                epoch=row.epoch,
            )
            for row in rows
        ]

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
        statement = text(
            """
            INSERT INTO reprocessing_jobs (
                job_type,
                payload,
                status,
                attempt_count,
                correlation_id,
                correlation_missing_reason,
                alternate_lookup_key
            )
            VALUES (
                'RESET_FX_WATERMARKS',
                json_build_object(
                    'from_currency', :from_currency,
                    'to_currency', :to_currency,
                    'earliest_impacted_date', CAST(:effective_date AS date)::text,
                    'content_hash', :content_hash,
                    'generated_at', :generated_at
                )::json,
                'PENDING',
                0,
                :correlation_id,
                :correlation_missing_reason,
                :alternate_lookup_key
            )
            ON CONFLICT ((payload->>'from_currency'), (payload->>'to_currency'))
            WHERE job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'
            DO UPDATE SET
                payload = json_build_object(
                    'from_currency', :from_currency,
                    'to_currency', :to_currency,
                    'earliest_impacted_date', LEAST(
                        (reprocessing_jobs.payload->>'earliest_impacted_date')::date,
                        CAST(:effective_date AS date)
                    )::text,
                    'content_hash', CASE
                        WHEN ROW(
                            CAST(:generated_at AS timestamptz),
                            :content_hash
                        ) > ROW(
                            COALESCE(
                                CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                                '-infinity'::timestamptz
                            ),
                            COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                        )
                        THEN :content_hash
                        ELSE reprocessing_jobs.payload->>'content_hash'
                    END,
                    'generated_at', CASE
                        WHEN ROW(
                            CAST(:generated_at AS timestamptz),
                            :content_hash
                        ) > ROW(
                            COALESCE(
                                CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                                '-infinity'::timestamptz
                            ),
                            COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                        )
                        THEN :generated_at
                        ELSE reprocessing_jobs.payload->>'generated_at'
                    END
                )::json,
                correlation_id = CASE
                    WHEN ROW(
                        CAST(:generated_at AS timestamptz),
                        :content_hash
                    ) > ROW(
                        COALESCE(
                            CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                            '-infinity'::timestamptz
                        ),
                        COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                    )
                    THEN COALESCE(:correlation_id, reprocessing_jobs.correlation_id)
                    ELSE reprocessing_jobs.correlation_id
                END,
                correlation_missing_reason = CASE
                    WHEN ROW(
                        CAST(:generated_at AS timestamptz),
                        :content_hash
                    ) <= ROW(
                        COALESCE(
                            CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                            '-infinity'::timestamptz
                        ),
                        COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                    ) THEN reprocessing_jobs.correlation_missing_reason
                    WHEN :correlation_id IS NOT NULL THEN NULL
                    ELSE reprocessing_jobs.correlation_missing_reason
                END,
                alternate_lookup_key = CASE
                    WHEN ROW(
                        CAST(:generated_at AS timestamptz),
                        :content_hash
                    ) <= ROW(
                        COALESCE(
                            CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                            '-infinity'::timestamptz
                        ),
                        COALESCE(reprocessing_jobs.payload->>'content_hash', '')
                    ) THEN reprocessing_jobs.alternate_lookup_key
                    WHEN :correlation_id IS NOT NULL THEN NULL
                    ELSE reprocessing_jobs.alternate_lookup_key
                END,
                updated_at = now()
            """
        ).bindparams(
            bindparam("from_currency", type_=String()),
            bindparam("to_currency", type_=String()),
            bindparam("effective_date", type_=Date()),
            bindparam("content_hash", type_=String()),
            bindparam("generated_at", type_=String()),
            bindparam("correlation_id", type_=String()),
            bindparam("correlation_missing_reason", type_=String()),
            bindparam("alternate_lookup_key", type_=String()),
        )
        await self._db.execute(
            statement,
            {
                "from_currency": correction.pair.from_currency,
                "to_currency": correction.pair.to_currency,
                "effective_date": correction.effective_date,
                "content_hash": correction.content_hash,
                "generated_at": correction.generated_at.isoformat(),
                "correlation_id": diagnostics.correlation_id,
                "correlation_missing_reason": diagnostics.correlation_missing_reason,
                "alternate_lookup_key": diagnostics.alternate_lookup_key,
            },
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
