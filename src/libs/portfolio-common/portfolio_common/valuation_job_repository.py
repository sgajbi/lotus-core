# src/libs/portfolio-common/portfolio_common/valuation_job_repository.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy import and_, func, not_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import PortfolioValuationJob

logger = logging.getLogger(__name__)


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
    ) -> None:
        """
        Idempotently creates or updates a valuation job.

        Duplicate scheduler polls for the same logical run must not re-arm an already completed
        valuation job. A genuinely new replay/backfill run is allowed to re-arm the job via a
        different correlation id.
        """
        try:
            latest_epoch = await self.get_latest_epoch_for_scope(
                portfolio_id=portfolio_id,
                security_id=security_id,
                valuation_date=valuation_date,
            )
            if latest_epoch is not None and latest_epoch > epoch:
                logger.info(
                    "Skipping stale valuation job upsert because a newer epoch already exists",
                    extra={
                        "portfolio_id": portfolio_id,
                        "security_id": security_id,
                        "valuation_date": valuation_date,
                        "incoming_epoch": epoch,
                        "latest_epoch": latest_epoch,
                    },
                )
                return

            job_data = {
                "portfolio_id": portfolio_id,
                "security_id": security_id,
                "valuation_date": valuation_date,
                "epoch": epoch,
                "status": "PENDING",
                "correlation_id": correlation_id,
            }

            stmt = pg_insert(PortfolioValuationJob).values(**job_data)

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
                        PortfolioValuationJob.correlation_id.is_not_distinct_from(correlation_id),
                    )
                ),
            )

            await self.db.execute(final_stmt)
            logger.debug(
                "Staged upsert for valuation job",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "valuation_date": valuation_date,
                    "epoch": epoch,
                },
            )
        except Exception:
            logger.error(
                "Failed to stage upsert for valuation job",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "valuation_date": valuation_date,
                },
                exc_info=True,
            )
            raise

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
