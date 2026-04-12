# src/libs/portfolio-common/portfolio_common/valuation_job_repository.py
import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, func, not_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import PortfolioValuationJob
from .logging_utils import normalize_lineage_value

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ValuationJobUpsert:
    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int
    correlation_id: Optional[str] = None


class ValuationJobRepository:
    """
    Handles database operations for creating and managing PortfolioValuationJob records.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_job(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        correlation_id: Optional[str] = None,
    ) -> int:
        """
        Idempotently creates or updates a valuation job.

        Duplicate scheduler polls for the same logical run must not re-arm an already completed
        valuation job. A genuinely new replay/backfill run is allowed to re-arm the job via a
        different correlation id.
        """
        return await self.upsert_jobs(
            [
                ValuationJobUpsert(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    valuation_date=valuation_date,
                    epoch=epoch,
                    correlation_id=correlation_id,
                )
            ]
        )

    async def upsert_jobs(self, jobs: Iterable[ValuationJobUpsert]) -> int:
        normalized_jobs = self._normalize_jobs(jobs)
        if not normalized_jobs:
            return 0

        try:
            latest_epochs_by_scope = await self.get_latest_epochs_for_scopes(normalized_jobs)
            eligible_jobs = [
                job
                for job in normalized_jobs
                if not self._is_stale_job(job, latest_epochs_by_scope)
            ]

            if not eligible_jobs:
                return 0

            stmt = pg_insert(PortfolioValuationJob).values(
                [
                    {
                        "portfolio_id": job.portfolio_id,
                        "security_id": job.security_id,
                        "valuation_date": job.valuation_date,
                        "epoch": job.epoch,
                        "status": "PENDING",
                        "correlation_id": job.correlation_id,
                    }
                    for job in eligible_jobs
                ]
            )

            update_dict = {
                "status": "PENDING",
                "correlation_id": stmt.excluded.correlation_id,
                "updated_at": func.now(),
            }

            final_stmt = stmt.on_conflict_do_update(
                index_elements=["portfolio_id", "security_id", "valuation_date", "epoch"],
                set_=update_dict,
                where=not_(
                    and_(
                        PortfolioValuationJob.status == "COMPLETE",
                        PortfolioValuationJob.correlation_id.is_not_distinct_from(
                            stmt.excluded.correlation_id
                        ),
                    )
                ),
            )

            result = await self.db.execute(
                final_stmt.returning(
                    PortfolioValuationJob.portfolio_id,
                    PortfolioValuationJob.security_id,
                    PortfolioValuationJob.valuation_date,
                    PortfolioValuationJob.epoch,
                )
            )
            staged_count = len(result.all())
            superseded_count = await self._skip_superseded_pending_jobs(
                normalized_jobs=normalized_jobs,
                latest_epochs_by_scope=latest_epochs_by_scope,
            )
            logger.debug(
                "Staged valuation job upserts",
                extra={
                    "requested_count": len(normalized_jobs),
                    "eligible_count": len(eligible_jobs),
                    "staged_count": staged_count,
                    "superseded_count": superseded_count,
                },
            )
            return staged_count
        except Exception:
            logger.error(
                "Failed to stage valuation job upserts",
                extra={
                    "job_count": len(normalized_jobs),
                },
                exc_info=True,
            )
            raise

    def _normalize_jobs(self, jobs: Iterable[ValuationJobUpsert]) -> list[ValuationJobUpsert]:
        normalized_by_scope: dict[tuple[str, str, date, int], ValuationJobUpsert] = {}
        for job in jobs:
            normalized_job = ValuationJobUpsert(
                portfolio_id=job.portfolio_id,
                security_id=job.security_id,
                valuation_date=job.valuation_date,
                epoch=job.epoch,
                correlation_id=normalize_lineage_value(job.correlation_id),
            )
            normalized_by_scope[
                (
                    normalized_job.portfolio_id,
                    normalized_job.security_id,
                    normalized_job.valuation_date,
                    normalized_job.epoch,
                )
            ] = normalized_job
        return list(normalized_by_scope.values())

    def _is_stale_job(
        self,
        job: ValuationJobUpsert,
        latest_epochs_by_scope: dict[tuple[str, str, date], int],
    ) -> bool:
        latest_epoch = latest_epochs_by_scope.get(
            (job.portfolio_id, job.security_id, job.valuation_date)
        )
        if latest_epoch is not None and latest_epoch > job.epoch:
            logger.info(
                "Skipping stale valuation job upsert because a newer epoch already exists",
                extra={
                    "portfolio_id": job.portfolio_id,
                    "security_id": job.security_id,
                    "valuation_date": job.valuation_date,
                    "incoming_epoch": job.epoch,
                    "latest_epoch": latest_epoch,
                },
            )
            return True
        return False

    async def get_latest_epoch_for_scope(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
    ) -> int | None:
        result = await self.db.execute(
            select(func.max(PortfolioValuationJob.epoch)).where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.security_id == security_id,
                PortfolioValuationJob.valuation_date == valuation_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_epochs_for_scopes(
        self, jobs: Iterable[ValuationJobUpsert]
    ) -> dict[tuple[str, str, date], int]:
        scopes = list(
            {
                (job.portfolio_id, job.security_id, job.valuation_date)
                for job in jobs
            }
        )
        if not scopes:
            return {}

        result = await self.db.execute(
            select(
                PortfolioValuationJob.portfolio_id,
                PortfolioValuationJob.security_id,
                PortfolioValuationJob.valuation_date,
                func.max(PortfolioValuationJob.epoch),
            )
            .where(
                tuple_(
                    PortfolioValuationJob.portfolio_id,
                    PortfolioValuationJob.security_id,
                    PortfolioValuationJob.valuation_date,
                ).in_(scopes)
            )
            .group_by(
                PortfolioValuationJob.portfolio_id,
                PortfolioValuationJob.security_id,
                PortfolioValuationJob.valuation_date,
            )
        )

        return {
            (portfolio_id, security_id, valuation_date): latest_epoch
            for portfolio_id, security_id, valuation_date, latest_epoch in result.all()
        }

    async def _skip_superseded_pending_jobs(
        self,
        *,
        normalized_jobs: list[ValuationJobUpsert],
        latest_epochs_by_scope: dict[tuple[str, str, date], int],
    ) -> int:
        latest_epoch_targets: dict[tuple[str, str, date], int] = {}
        for job in normalized_jobs:
            scope = (job.portfolio_id, job.security_id, job.valuation_date)
            latest_epoch_targets[scope] = max(
                latest_epochs_by_scope.get(scope, job.epoch),
                latest_epoch_targets.get(scope, job.epoch),
                job.epoch,
            )

        skipped_count = 0
        for (
            portfolio_id,
            security_id,
            valuation_date,
        ), latest_epoch in latest_epoch_targets.items():
            stmt = (
                update(PortfolioValuationJob)
                .where(
                    PortfolioValuationJob.portfolio_id == portfolio_id,
                    PortfolioValuationJob.security_id == security_id,
                    PortfolioValuationJob.valuation_date == valuation_date,
                    PortfolioValuationJob.status == "PENDING",
                    PortfolioValuationJob.epoch < latest_epoch,
                )
                .values(
                    status="SKIPPED_SUPERSEDED",
                    failure_reason="Superseded by newer valuation epoch.",
                    updated_at=func.now(),
                )
                .returning(PortfolioValuationJob.id)
            )
            result = await self.db.execute(stmt)
            skipped_count += len(result.fetchall())
        return skipped_count
