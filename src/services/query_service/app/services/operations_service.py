import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.operations_dto import (
    CalculatorSloBucket,
    CalculatorSloResponse,
    LineageKeyListResponse,
    LineageKeyRecord,
    LineageResponse,
    ReprocessingSloBucket,
    SupportJobListResponse,
    SupportJobRecord,
    SupportOverviewResponse,
)
from ..repositories.operations_repository import OperationsRepository


class OperationsService:
    def __init__(self, db: AsyncSession):
        self.repo = OperationsRepository(db)

    async def _ensure_portfolio_exists(self, portfolio_id: str) -> None:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

    async def get_support_overview(self, portfolio_id: str) -> SupportOverviewResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        (
            latest_business_date,
            current_epoch,
            active_reprocessing_keys,
            pending_valuation_jobs,
            processing_valuation_jobs,
            stale_processing_valuation_jobs,
            oldest_pending_valuation_date,
            pending_aggregation_jobs,
            latest_transaction_date,
            latest_position_snapshot_date_unbounded,
            position_snapshot_history_mismatch_count,
        ) = await asyncio.gather(
            self.repo.get_latest_business_date(),
            self.repo.get_current_portfolio_epoch(portfolio_id),
            self.repo.get_active_reprocessing_keys_count(portfolio_id),
            self.repo.get_pending_valuation_jobs_count(portfolio_id),
            self.repo.get_processing_valuation_jobs_count(portfolio_id),
            self.repo.get_stale_processing_valuation_jobs_count(portfolio_id, stale_minutes=15),
            self.repo.get_oldest_pending_valuation_date(portfolio_id),
            self.repo.get_pending_aggregation_jobs_count(portfolio_id),
            self.repo.get_latest_transaction_date(portfolio_id),
            self.repo.get_latest_snapshot_date_for_current_epoch(portfolio_id),
            self.repo.get_position_snapshot_history_mismatch_count(portfolio_id),
        )

        latest_booked_transaction_date = None
        latest_booked_position_snapshot_date = None
        if latest_business_date is not None:
            (
                latest_booked_transaction_date,
                latest_booked_position_snapshot_date,
            ) = await asyncio.gather(
                self.repo.get_latest_transaction_date_as_of(
                    portfolio_id, latest_business_date
                ),
                self.repo.get_latest_snapshot_date_for_current_epoch_as_of(
                    portfolio_id, latest_business_date
                ),
            )

        valuation_backlog_age_days = None
        if oldest_pending_valuation_date:
            reference_date = latest_business_date or datetime.now(timezone.utc).date()
            valuation_backlog_age_days = max(
                0, (reference_date - oldest_pending_valuation_date).days
            )

        return SupportOverviewResponse(
            portfolio_id=portfolio_id,
            business_date=latest_business_date,
            current_epoch=current_epoch,
            active_reprocessing_keys=active_reprocessing_keys,
            pending_valuation_jobs=pending_valuation_jobs,
            processing_valuation_jobs=processing_valuation_jobs,
            stale_processing_valuation_jobs=stale_processing_valuation_jobs,
            oldest_pending_valuation_date=oldest_pending_valuation_date,
            valuation_backlog_age_days=valuation_backlog_age_days,
            pending_aggregation_jobs=pending_aggregation_jobs,
            latest_transaction_date=latest_transaction_date,
            latest_booked_transaction_date=latest_booked_transaction_date,
            latest_position_snapshot_date=latest_position_snapshot_date_unbounded,
            latest_booked_position_snapshot_date=latest_booked_position_snapshot_date,
            position_snapshot_history_mismatch_count=position_snapshot_history_mismatch_count,
        )

    async def get_calculator_slos(
        self, portfolio_id: str, stale_threshold_minutes: int = 15
    ) -> CalculatorSloResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        (
            latest_business_date,
            active_reprocessing_keys,
            valuation_pending,
            valuation_processing,
            valuation_stale_processing,
            valuation_failed,
            valuation_failed_last_24h,
            valuation_oldest_open,
            aggregation_pending,
            aggregation_processing,
            aggregation_stale_processing,
            aggregation_failed,
            aggregation_failed_last_24h,
            aggregation_oldest_open,
        ) = await asyncio.gather(
            self.repo.get_latest_business_date(),
            self.repo.get_active_reprocessing_keys_count(portfolio_id),
            self.repo.get_pending_valuation_jobs_count(portfolio_id),
            self.repo.get_processing_valuation_jobs_count(portfolio_id),
            self.repo.get_stale_processing_valuation_jobs_count(
                portfolio_id, stale_minutes=stale_threshold_minutes
            ),
            self.repo.get_valuation_failed_jobs_count(portfolio_id),
            self.repo.get_valuation_failed_jobs_last_hours(portfolio_id, hours=24),
            self.repo.get_oldest_pending_valuation_date(portfolio_id),
            self.repo.get_pending_aggregation_jobs_count(portfolio_id),
            self.repo.get_processing_aggregation_jobs_count(portfolio_id),
            self.repo.get_stale_processing_aggregation_jobs_count(
                portfolio_id, stale_minutes=stale_threshold_minutes
            ),
            self.repo.get_aggregation_failed_jobs_count(portfolio_id),
            self.repo.get_aggregation_failed_jobs_last_hours(portfolio_id, hours=24),
            self.repo.get_oldest_pending_aggregation_date(portfolio_id),
        )

        reference_date = latest_business_date or datetime.now(timezone.utc).date()
        valuation_backlog_age_days = (
            max(0, (reference_date - valuation_oldest_open).days)
            if valuation_oldest_open is not None
            else None
        )
        aggregation_backlog_age_days = (
            max(0, (reference_date - aggregation_oldest_open).days)
            if aggregation_oldest_open is not None
            else None
        )

        return CalculatorSloResponse(
            portfolio_id=portfolio_id,
            business_date=latest_business_date,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=datetime.now(timezone.utc),
            valuation=CalculatorSloBucket(
                pending_jobs=valuation_pending,
                processing_jobs=valuation_processing,
                stale_processing_jobs=valuation_stale_processing,
                failed_jobs=valuation_failed,
                failed_jobs_last_24h=valuation_failed_last_24h,
                oldest_open_job_date=valuation_oldest_open,
                backlog_age_days=valuation_backlog_age_days,
            ),
            aggregation=CalculatorSloBucket(
                pending_jobs=aggregation_pending,
                processing_jobs=aggregation_processing,
                stale_processing_jobs=aggregation_stale_processing,
                failed_jobs=aggregation_failed,
                failed_jobs_last_24h=aggregation_failed_last_24h,
                oldest_open_job_date=aggregation_oldest_open,
                backlog_age_days=aggregation_backlog_age_days,
            ),
            reprocessing=ReprocessingSloBucket(active_reprocessing_keys=active_reprocessing_keys),
        )

    async def get_lineage(self, portfolio_id: str, security_id: str) -> LineageResponse:
        position_state = await self.repo.get_position_state(portfolio_id, security_id)
        if not position_state:
            raise ValueError(
                "Lineage state not found for portfolio "
                f"'{portfolio_id}' and security '{security_id}'"
            )

        (
            latest_history_date,
            latest_snapshot_date,
            latest_valuation_job,
        ) = await asyncio.gather(
            self.repo.get_latest_position_history_date(
                portfolio_id, security_id, position_state.epoch
            ),
            self.repo.get_latest_daily_snapshot_date(
                portfolio_id, security_id, position_state.epoch
            ),
            self.repo.get_latest_valuation_job(
                portfolio_id, security_id, position_state.epoch
            ),
        )

        return LineageResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=position_state.epoch,
            watermark_date=position_state.watermark_date,
            reprocessing_status=position_state.status,
            latest_position_history_date=latest_history_date,
            latest_daily_snapshot_date=latest_snapshot_date,
            latest_valuation_job_date=(
                latest_valuation_job.valuation_date if latest_valuation_job else None
            ),
            latest_valuation_job_status=(
                latest_valuation_job.status if latest_valuation_job else None
            ),
        )

    async def get_lineage_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        reprocessing_status: str | None = None,
        security_id: str | None = None,
    ) -> LineageKeyListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, keys = await asyncio.gather(
            self.repo.get_lineage_keys_count(
                portfolio_id=portfolio_id,
                reprocessing_status=reprocessing_status,
                security_id=security_id,
            ),
            self.repo.get_lineage_keys(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                reprocessing_status=reprocessing_status,
                security_id=security_id,
            ),
        )
        return LineageKeyListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                LineageKeyRecord(
                    security_id=k.security_id,
                    epoch=k.epoch,
                    watermark_date=k.watermark_date,
                    reprocessing_status=k.status,
                )
                for k in keys
            ],
        )

    async def get_valuation_jobs(
        self, portfolio_id: str, skip: int, limit: int, status: str | None = None
    ) -> SupportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, jobs = await asyncio.gather(
            self.repo.get_valuation_jobs_count(portfolio_id=portfolio_id, status=status),
            self.repo.get_valuation_jobs(
                portfolio_id=portfolio_id, skip=skip, limit=limit, status=status
            ),
        )
        return SupportJobListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                SupportJobRecord(
                    job_type="VALUATION",
                    business_date=job.valuation_date,
                    status=job.status,
                    security_id=job.security_id,
                    epoch=job.epoch,
                    attempt_count=job.attempt_count,
                    failure_reason=job.failure_reason,
                )
                for job in jobs
            ],
        )

    async def get_aggregation_jobs(
        self, portfolio_id: str, skip: int, limit: int, status: str | None = None
    ) -> SupportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, jobs = await asyncio.gather(
            self.repo.get_aggregation_jobs_count(portfolio_id=portfolio_id, status=status),
            self.repo.get_aggregation_jobs(
                portfolio_id=portfolio_id, skip=skip, limit=limit, status=status
            ),
        )
        return SupportJobListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                SupportJobRecord(
                    job_type="AGGREGATION",
                    business_date=job.aggregation_date,
                    status=job.status,
                    security_id=None,
                    epoch=None,
                    attempt_count=None,
                    failure_reason=None,
                )
                for job in jobs
            ],
        )
