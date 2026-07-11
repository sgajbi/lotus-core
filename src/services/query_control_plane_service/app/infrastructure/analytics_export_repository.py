"""SQLAlchemy persistence adapter for durable analytics export jobs."""

from __future__ import annotations

from datetime import UTC, datetime

from portfolio_common.database_models import AnalyticsExportJob as AnalyticsExportJobModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.analytics import AnalyticsExportJobRecord


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
    ) -> AnalyticsExportJobRecord:
        row = AnalyticsExportJobModel(
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
        return _export_job_record(row)

    async def get_job(self, job_id: str) -> AnalyticsExportJobRecord | None:
        row = await self._get_model(job_id)
        return _export_job_record(row) if row is not None else None

    async def get_latest_by_fingerprint(
        self, *, request_fingerprint: str, dataset_type: str
    ) -> AnalyticsExportJobRecord | None:
        result = await self.db.execute(
            select(AnalyticsExportJobModel)
            .where(
                AnalyticsExportJobModel.request_fingerprint == request_fingerprint,
                AnalyticsExportJobModel.dataset_type == dataset_type,
            )
            .order_by(AnalyticsExportJobModel.id.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return _export_job_record(row) if row is not None else None

    async def mark_running(self, row: AnalyticsExportJobRecord) -> AnalyticsExportJobRecord:
        model = await self._require_model(row.job_id)
        model.status = "running"
        model.started_at = datetime.now(UTC)
        await self.db.flush()
        return _export_job_record(model)

    async def mark_completed(
        self, row: AnalyticsExportJobRecord, *, result_payload: dict, result_row_count: int
    ) -> AnalyticsExportJobRecord:
        model = await self._require_model(row.job_id)
        model.status = "completed"
        model.result_payload = result_payload
        model.result_row_count = result_row_count
        model.completed_at = datetime.now(UTC)
        await self.db.flush()
        return _export_job_record(model)

    async def mark_failed(
        self, row: AnalyticsExportJobRecord, *, error_message: str
    ) -> AnalyticsExportJobRecord:
        model = await self._require_model(row.job_id)
        model.status = "failed"
        model.error_message = error_message
        model.completed_at = datetime.now(UTC)
        await self.db.flush()
        return _export_job_record(model)

    async def _get_model(self, job_id: str) -> AnalyticsExportJobModel | None:
        result = await self.db.execute(
            select(AnalyticsExportJobModel).where(AnalyticsExportJobModel.job_id == job_id).limit(1)
        )
        return result.scalars().first()

    async def _require_model(self, job_id: str) -> AnalyticsExportJobModel:
        row = await self._get_model(job_id)
        if row is None:
            raise LookupError(f"Analytics export job {job_id!r} no longer exists.")
        return row


def _export_job_record(row: AnalyticsExportJobModel) -> AnalyticsExportJobRecord:
    return AnalyticsExportJobRecord(
        job_id=row.job_id,
        dataset_type=row.dataset_type,
        portfolio_id=row.portfolio_id,
        status=row.status,
        request_fingerprint=row.request_fingerprint,
        request_payload=dict(row.request_payload),
        result_payload=dict(row.result_payload) if row.result_payload is not None else None,
        result_row_count=row.result_row_count,
        result_format=row.result_format,
        compression=row.compression,
        error_message=row.error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        updated_at=row.updated_at,
    )
