# src/libs/portfolio-common/portfolio_common/valuation_job_repository.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy import func
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
        Idempotently creates or updates a valuation job, setting its status to 'PENDING'.
        If a job for the same key (including epoch) exists, it will be reset to 'PENDING'.
        """
        try:
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
