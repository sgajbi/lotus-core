from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService


@dataclass(frozen=True)
class IngestionOperationsNotFound(Exception):
    code: str
    message: str


@dataclass(frozen=True)
class IngestionJobsPage:
    jobs: list[Any]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class IngestionJobFailuresPage:
    failures: list[Any]
    total: int


@dataclass(frozen=True)
class ConsumerDlqEventsPage:
    events: list[Any]
    total: int


@dataclass(frozen=True)
class IngestionReplayAuditsPage:
    audits: list[Any]
    total: int


@dataclass(frozen=True)
class IngestionOperationsQueryService:
    ingestion_job_service: IngestionJobService

    async def list_jobs(
        self,
        *,
        status: Any | None,
        entity_type: str | None,
        submitted_from: datetime | None,
        submitted_to: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> IngestionJobsPage:
        jobs, next_cursor = await self.ingestion_job_service.list_jobs(
            status=status,
            entity_type=entity_type,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            cursor=cursor,
            limit=limit,
        )
        return IngestionJobsPage(jobs=jobs, total=len(jobs), next_cursor=next_cursor)

    async def list_job_failures(
        self,
        *,
        job_id: str,
        limit: int,
    ) -> IngestionJobFailuresPage:
        await self._require_job(job_id)
        failures = await self.ingestion_job_service.list_failures(job_id=job_id, limit=limit)
        return IngestionJobFailuresPage(failures=failures, total=len(failures))

    async def get_job_record_status(self, job_id: str) -> Any:
        record_status = await self.ingestion_job_service.get_job_record_status(job_id)
        if record_status is None:
            raise self._job_not_found(job_id)
        return record_status

    async def list_consumer_dlq_events(
        self,
        *,
        limit: int,
        original_topic: str | None,
        consumer_group: str | None,
    ) -> ConsumerDlqEventsPage:
        events = await self.ingestion_job_service.list_consumer_dlq_events(
            limit=limit,
            original_topic=original_topic,
            consumer_group=consumer_group,
        )
        return ConsumerDlqEventsPage(events=events, total=len(events))

    async def list_replay_audits(
        self,
        *,
        limit: int,
        recovery_path: str | None,
        replay_status: str | None,
        replay_fingerprint: str | None,
        job_id: str | None,
    ) -> IngestionReplayAuditsPage:
        audits = await self.ingestion_job_service.list_replay_audits(
            limit=limit,
            recovery_path=recovery_path,
            replay_status=replay_status,
            replay_fingerprint=replay_fingerprint,
            job_id=job_id,
        )
        return IngestionReplayAuditsPage(audits=audits, total=len(audits))

    async def get_replay_audit(self, replay_id: str) -> Any:
        audit = await self.ingestion_job_service.get_replay_audit(replay_id)
        if audit is None:
            raise IngestionOperationsNotFound(
                code="INGESTION_REPLAY_AUDIT_NOT_FOUND",
                message=f"Replay audit '{replay_id}' was not found.",
            )
        return audit

    async def _require_job(self, job_id: str) -> Any:
        job = await self.ingestion_job_service.get_job(job_id)
        if job is None:
            raise self._job_not_found(job_id)
        return job

    def _job_not_found(self, job_id: str) -> IngestionOperationsNotFound:
        return IngestionOperationsNotFound(
            code="INGESTION_JOB_NOT_FOUND",
            message=f"Ingestion job '{job_id}' was not found.",
        )
