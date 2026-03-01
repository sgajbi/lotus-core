from __future__ import annotations

from datetime import UTC, datetime

from portfolio_common.database_models import AnalyticsExportJob
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsExportRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        *,
        job_id: str,
        dataset_type: str,
        portfolio_id: str,
        request_fingerprint: str,
        request_payload: dict,
        result_format: str,
        compression: str,
    ) -> AnalyticsExportJob:
        row = AnalyticsExportJob(
            job_id=job_id,
            dataset_type=dataset_type,
            portfolio_id=portfolio_id,
            status="accepted",
            request_fingerprint=request_fingerprint,
            request_payload=request_payload,
            result_format=result_format,
            compression=compression,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_job(self, job_id: str) -> AnalyticsExportJob | None:
        result = await self.db.execute(
            select(AnalyticsExportJob).where(AnalyticsExportJob.job_id == job_id).limit(1)
        )
        return result.scalars().first()

    async def get_latest_by_fingerprint(
        self, *, request_fingerprint: str, dataset_type: str
    ) -> AnalyticsExportJob | None:
        result = await self.db.execute(
            select(AnalyticsExportJob)
            .where(
                AnalyticsExportJob.request_fingerprint == request_fingerprint,
                AnalyticsExportJob.dataset_type == dataset_type,
            )
            .order_by(AnalyticsExportJob.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def mark_running(self, row: AnalyticsExportJob) -> None:
        row.status = "running"
        row.started_at = datetime.now(UTC)
        await self.db.flush()

    async def mark_completed(
        self, row: AnalyticsExportJob, *, result_payload: dict, result_row_count: int
    ) -> None:
        row.status = "completed"
        row.result_payload = result_payload
        row.result_row_count = result_row_count
        row.completed_at = datetime.now(UTC)
        await self.db.flush()

    async def mark_failed(self, row: AnalyticsExportJob, *, error_message: str) -> None:
        row.status = "failed"
        row.error_message = error_message
        row.completed_at = datetime.now(UTC)
        await self.db.flush()
