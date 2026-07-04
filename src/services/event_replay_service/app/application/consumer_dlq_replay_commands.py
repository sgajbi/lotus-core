from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService

from .ingestion_retry_commands import ReplayCommandError
from .replay_payload_dispatcher import ReplayPayloadDispatcher
from .replay_retry_payloads import deterministic_replay_fingerprint, payload_record_count

logger = logging.getLogger(__name__)

HTTP_NOT_FOUND = 404
HTTP_INTERNAL_SERVER_ERROR = 500

CONSUMER_DLQ_REPLAY_RECOVERY_PATH = "consumer_dlq_replay"


@dataclass(frozen=True)
class ConsumerDlqReplayCommand:
    dry_run: bool
    requested_by: str | None


@dataclass(frozen=True)
class ConsumerDlqReplayResult:
    event_id: str
    correlation_id: str | None
    correlation_missing_reason: str | None
    alternate_lookup_key: str | None
    job_id: str | None
    replay_status: str
    replay_audit_id: str
    replay_fingerprint: str
    message: str

    def to_response_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConsumerDlqReplayCandidate:
    job_id: str
    context: Any
    replay_fingerprint: str


@dataclass(frozen=True)
class ConsumerDlqReplayCommandService:
    ingestion_job_service: IngestionJobService
    replay_payload_dispatcher: ReplayPayloadDispatcher

    async def replay_consumer_dlq_event(
        self,
        *,
        event_id: str,
        command: ConsumerDlqReplayCommand,
    ) -> ConsumerDlqReplayResult:
        event = await self._required_consumer_dlq_event(event_id)
        if not event.correlation_id:
            correlation_missing_reason = self._consumer_dlq_correlation_missing_reason(event)
            alternate_lookup_key = self._consumer_dlq_alternate_lookup_key(event)
            return await self._consumer_dlq_not_replayable_result(
                event_id=event_id,
                correlation_id=None,
                correlation_missing_reason=correlation_missing_reason,
                alternate_lookup_key=alternate_lookup_key,
                job_id=None,
                endpoint=None,
                dry_run=command.dry_run,
                replay_reason=(
                    "DLQ event has no correlation id and cannot be mapped to ingestion payload. "
                    f"Missing reason: {correlation_missing_reason}; "
                    f"alternate lookup key: {alternate_lookup_key}."
                ),
                requested_by=command.requested_by,
            )

        replay_candidate = await self._consumer_dlq_replay_candidate_or_result(
            event_id=event_id,
            correlation_id=event.correlation_id,
            dry_run=command.dry_run,
            requested_by=command.requested_by,
        )
        if isinstance(replay_candidate, ConsumerDlqReplayResult):
            return replay_candidate

        duplicate_result = await self._consumer_dlq_duplicate_replay_result(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=replay_candidate.job_id,
            context=replay_candidate.context,
            replay_fingerprint=replay_candidate.replay_fingerprint,
            dry_run=command.dry_run,
            requested_by=command.requested_by,
        )
        if duplicate_result is not None:
            return duplicate_result

        await self.ingestion_job_service.assert_retry_allowed_for_records(
            submitted_at=replay_candidate.context.submitted_at,
            replay_record_count=payload_record_count(replay_candidate.context.request_payload),
        )
        if command.dry_run:
            return await self._record_consumer_dlq_replay_result(
                event_id=event_id,
                correlation_id=event.correlation_id,
                job_id=replay_candidate.job_id,
                endpoint=replay_candidate.context.endpoint,
                replay_fingerprint=replay_candidate.replay_fingerprint,
                replay_status="dry_run",
                dry_run=True,
                replay_reason="Dry-run successful. Correlated ingestion job is replayable.",
                message="Dry-run successful. Correlated ingestion job is replayable.",
                requested_by=command.requested_by,
            )

        await self._publish_consumer_dlq_replay(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=replay_candidate.job_id,
            context=replay_candidate.context,
            replay_fingerprint=replay_candidate.replay_fingerprint,
            requested_by=command.requested_by,
        )
        return await self._mark_consumer_dlq_replay_replayed(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=replay_candidate.job_id,
            context=replay_candidate.context,
            replay_fingerprint=replay_candidate.replay_fingerprint,
            requested_by=command.requested_by,
        )

    async def _required_consumer_dlq_event(self, event_id: str) -> Any:
        event = await self.ingestion_job_service.get_consumer_dlq_event(event_id)
        if event is None:
            raise ReplayCommandError(
                HTTP_NOT_FOUND,
                {
                    "code": "INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND",
                    "message": f"Consumer DLQ event '{event_id}' was not found.",
                },
            )
        return event

    def _consumer_dlq_correlation_missing_reason(self, event: Any) -> str:
        reason = getattr(event, "correlation_missing_reason", None)
        return reason or "message_correlation_id_absent"

    def _consumer_dlq_alternate_lookup_key(self, event: Any) -> str:
        lookup_key = getattr(event, "alternate_lookup_key", None)
        if lookup_key:
            return lookup_key
        original_key = getattr(event, "original_key", None) or "unkeyed"
        return (
            f"consumer_dlq|topic={getattr(event, 'original_topic', 'unknown')}|"
            f"group={getattr(event, 'consumer_group', 'unknown')}|"
            f"dlq={getattr(event, 'dlq_topic', 'unknown')}|key={original_key}|"
            f"event={getattr(event, 'event_id', 'unknown')}"
        )

    def _replay_job_id(self, replay_job: Any) -> str:
        return str(self._job_field(replay_job, "job_id"))

    def _consumer_dlq_replay_fingerprint(
        self,
        *,
        event_id: str,
        correlation_id: str,
        replay_job_id: str,
        context: Any | None,
    ) -> str:
        return deterministic_replay_fingerprint(
            event_id=event_id,
            correlation_id=correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint if context else None,
            payload=context.request_payload if context else None,
            idempotency_key=context.idempotency_key if context else None,
        )

    async def _consumer_dlq_missing_payload_result(
        self,
        *,
        event_id: str,
        correlation_id: str,
        replay_job_id: str,
        context: Any | None,
        replay_fingerprint: str,
        dry_run: bool,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult:
        return await self._record_consumer_dlq_replay_result(
            event_id=event_id,
            correlation_id=correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint if context else None,
            replay_fingerprint=replay_fingerprint,
            replay_status="not_replayable",
            dry_run=dry_run,
            replay_reason="Correlated ingestion job does not have durable replay payload.",
            message="Correlated ingestion job does not have durable replay payload.",
            requested_by=requested_by,
        )

    async def _consumer_dlq_replay_candidate_or_result(
        self,
        *,
        event_id: str,
        correlation_id: str,
        dry_run: bool,
        requested_by: str | None,
    ) -> ConsumerDlqReplayCandidate | ConsumerDlqReplayResult:
        replay_job = await self._correlated_consumer_dlq_replay_job(
            correlation_id=correlation_id,
        )
        if replay_job is None:
            return await self._consumer_dlq_not_replayable_result(
                event_id=event_id,
                correlation_id=correlation_id,
                correlation_missing_reason=None,
                alternate_lookup_key=None,
                job_id=None,
                endpoint=None,
                dry_run=dry_run,
                replay_reason="No correlated ingestion job found for consumer DLQ event.",
                requested_by=requested_by,
            )

        replay_job_id = self._replay_job_id(replay_job)
        context = await self.ingestion_job_service.get_job_replay_context(replay_job_id)
        replay_fingerprint = self._consumer_dlq_replay_fingerprint(
            event_id=event_id,
            correlation_id=correlation_id,
            replay_job_id=replay_job_id,
            context=context,
        )
        if context is None or context.request_payload is None:
            return await self._consumer_dlq_missing_payload_result(
                event_id=event_id,
                correlation_id=correlation_id,
                replay_job_id=replay_job_id,
                context=context,
                replay_fingerprint=replay_fingerprint,
                dry_run=dry_run,
                requested_by=requested_by,
            )
        return ConsumerDlqReplayCandidate(
            job_id=replay_job_id,
            context=context,
            replay_fingerprint=replay_fingerprint,
        )

    async def _correlated_consumer_dlq_replay_job(
        self,
        *,
        correlation_id: str,
    ) -> Any | None:
        jobs, _ = await self.ingestion_job_service.list_jobs(limit=500)
        return next(
            (
                job
                for job in jobs
                if self._job_field(job, "correlation_id") == correlation_id
                and self._job_field(job, "status") in {"failed", "queued", "accepted"}
            ),
            None,
        )

    async def _consumer_dlq_not_replayable_result(
        self,
        *,
        event_id: str,
        correlation_id: str | None,
        correlation_missing_reason: str | None = None,
        alternate_lookup_key: str | None = None,
        job_id: str | None,
        endpoint: str | None,
        dry_run: bool,
        replay_reason: str,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult:
        replay_fingerprint = deterministic_replay_fingerprint(
            event_id=event_id,
            correlation_id=correlation_id,
            job_id=job_id,
            endpoint=endpoint,
            payload=None,
            idempotency_key=None,
            alternate_lookup_key=alternate_lookup_key,
        )
        return await self._record_consumer_dlq_replay_result(
            event_id=event_id,
            correlation_id=correlation_id,
            correlation_missing_reason=correlation_missing_reason,
            alternate_lookup_key=alternate_lookup_key,
            job_id=job_id,
            endpoint=endpoint,
            replay_fingerprint=replay_fingerprint,
            replay_status="not_replayable",
            dry_run=dry_run,
            replay_reason=replay_reason,
            message=replay_reason,
            requested_by=requested_by,
        )

    async def _record_consumer_dlq_replay_result(
        self,
        *,
        event_id: str,
        correlation_id: str | None,
        correlation_missing_reason: str | None = None,
        alternate_lookup_key: str | None = None,
        job_id: str | None,
        endpoint: str | None,
        replay_fingerprint: str,
        replay_status: str,
        dry_run: bool,
        replay_reason: str,
        message: str,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult:
        replay_audit_id = await self._record_mandatory_replay_audit(
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=correlation_id,
            job_id=job_id,
            endpoint=endpoint,
            replay_status=replay_status,
            dry_run=dry_run,
            replay_reason=replay_reason,
            requested_by=requested_by,
            correlation_missing_reason=correlation_missing_reason,
            alternate_lookup_key=alternate_lookup_key,
        )
        return ConsumerDlqReplayResult(
            event_id=event_id,
            correlation_id=correlation_id,
            correlation_missing_reason=correlation_missing_reason,
            alternate_lookup_key=alternate_lookup_key,
            job_id=job_id,
            replay_status=replay_status,
            replay_audit_id=replay_audit_id,
            replay_fingerprint=replay_fingerprint,
            message=message,
        )

    async def _consumer_dlq_duplicate_replay_result(
        self,
        *,
        event_id: str,
        correlation_id: str,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        dry_run: bool,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult | None:
        existing_success = (
            await self.ingestion_job_service.find_successful_replay_audit_by_fingerprint(
                replay_fingerprint,
                recovery_path=CONSUMER_DLQ_REPLAY_RECOVERY_PATH,
            )
        )
        if existing_success and not dry_run:
            return await self._record_consumer_dlq_replay_result(
                event_id=event_id,
                correlation_id=correlation_id,
                job_id=job_id,
                endpoint=context.endpoint,
                replay_fingerprint=replay_fingerprint,
                replay_status="duplicate_blocked",
                dry_run=False,
                replay_reason=(
                    "Replay blocked because this deterministic replay fingerprint was already "
                    f"replayed successfully (replay_id={existing_success['replay_id']})."
                ),
                message=(
                    "Replay blocked because an equivalent deterministic replay already succeeded."
                ),
                requested_by=requested_by,
            )
        return None

    async def _publish_consumer_dlq_replay(
        self,
        *,
        event_id: str,
        correlation_id: str,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> None:
        try:
            await self.replay_payload_dispatcher.replay_payload(
                endpoint=context.endpoint,
                payload=context.request_payload,
                idempotency_key=context.idempotency_key,
            )
        except Exception as exc:
            replay_audit_id = await self._record_mandatory_replay_audit(
                event_id=event_id,
                replay_fingerprint=replay_fingerprint,
                correlation_id=correlation_id,
                job_id=job_id,
                endpoint=context.endpoint,
                replay_status="failed",
                dry_run=False,
                replay_reason=str(exc),
                requested_by=requested_by,
            )
            raise ReplayCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                {
                    "code": "INGESTION_DLQ_REPLAY_FAILED",
                    "message": str(exc),
                    "replay_audit_id": replay_audit_id,
                },
            ) from exc

    async def _mark_consumer_dlq_replay_replayed(
        self,
        *,
        event_id: str,
        correlation_id: str,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult:
        try:
            await self.ingestion_job_service.mark_retried(job_id)
            await self.ingestion_job_service.mark_queued(job_id)
            return await self._record_consumer_dlq_replay_result(
                event_id=event_id,
                correlation_id=correlation_id,
                job_id=job_id,
                endpoint=context.endpoint,
                replay_fingerprint=replay_fingerprint,
                replay_status="replayed",
                dry_run=False,
                replay_reason="Replayed ingestion job from correlated consumer DLQ event.",
                message="Replayed ingestion job from correlated consumer DLQ event.",
                requested_by=requested_by,
            )
        except ReplayCommandError:
            raise
        except Exception as exc:
            replay_reason = f"Replay publish succeeded but post-publish bookkeeping failed: {exc}"
            replay_audit_id = await self._record_mandatory_replay_audit(
                event_id=event_id,
                replay_fingerprint=replay_fingerprint,
                correlation_id=correlation_id,
                job_id=job_id,
                endpoint=context.endpoint,
                replay_status="replayed_bookkeeping_failed",
                dry_run=False,
                replay_reason=replay_reason,
                requested_by=requested_by,
            )
            raise ReplayCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                {
                    "code": "INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED",
                    "message": replay_reason,
                    "replay_audit_id": replay_audit_id,
                    "replay_fingerprint": replay_fingerprint,
                },
            ) from exc

    async def _record_mandatory_replay_audit(
        self,
        *,
        event_id: str,
        replay_fingerprint: str,
        correlation_id: str | None,
        job_id: str | None,
        endpoint: str | None,
        replay_status: str,
        dry_run: bool,
        replay_reason: str,
        requested_by: str | None,
        correlation_missing_reason: str | None = None,
        alternate_lookup_key: str | None = None,
    ) -> str:
        try:
            return await self.ingestion_job_service.record_consumer_dlq_replay_audit(
                recovery_path=CONSUMER_DLQ_REPLAY_RECOVERY_PATH,
                event_id=event_id,
                replay_fingerprint=replay_fingerprint,
                correlation_id=correlation_id,
                job_id=job_id,
                endpoint=endpoint,
                replay_status=replay_status,
                dry_run=dry_run,
                replay_reason=replay_reason,
                requested_by=requested_by,
                correlation_missing_reason=correlation_missing_reason,
                alternate_lookup_key=alternate_lookup_key,
            )
        except Exception as exc:
            logger.exception(
                "Mandatory replay audit recording failed.",
                extra={
                    "recovery_path": CONSUMER_DLQ_REPLAY_RECOVERY_PATH,
                    "event_id": event_id,
                    "job_id": job_id,
                    "replay_status": replay_status,
                },
            )
            raise ReplayCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                {
                    "code": "INGESTION_REPLAY_AUDIT_WRITE_FAILED",
                    "message": (
                        "Replay audit could not be recorded; replay outcome was not acknowledged."
                    ),
                    "recovery_path": CONSUMER_DLQ_REPLAY_RECOVERY_PATH,
                    "event_id": event_id,
                    "job_id": job_id,
                    "replay_status": replay_status,
                    "replay_fingerprint": replay_fingerprint,
                },
            ) from exc

    def _job_field(self, job: Any, field: str) -> Any:
        if isinstance(job, dict):
            return job.get(field)
        return getattr(job, field, None)
