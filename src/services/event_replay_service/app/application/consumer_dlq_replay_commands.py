from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from portfolio_common.domain.tenant import TenantContext
from portfolio_common.ingestion_lineage import ingestion_job_scope

from src.services.ingestion_service.app.application.ingestion_failure_evidence import (
    project_ingestion_failure_evidence,
)
from src.services.ingestion_service.app.domain.ingestion_replay_evidence import (
    ReplayEvidenceFailure,
    replay_evidence_failure,
)
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService

from .replay_command_errors import ReplayCommandError
from .replay_payload_dispatcher import ReplayPayloadDispatcher
from .replay_retry_payloads import deterministic_replay_fingerprint, payload_record_count

logger = logging.getLogger(__name__)

HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_INTERNAL_SERVER_ERROR = 500

CONSUMER_DLQ_REPLAY_RECOVERY_PATH = "consumer_dlq_replay"


@dataclass(frozen=True)
class ConsumerDlqReplayCommand:
    tenant_context: TenantContext
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
        tenant_id = command.tenant_context.tenant_id_text
        event = await self._required_consumer_dlq_event(event_id, tenant_id=tenant_id)
        ingestion_job_id = getattr(event, "ingestion_job_id", None)
        if not event.correlation_id and not ingestion_job_id:
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
            ingestion_job_id=ingestion_job_id,
            dry_run=command.dry_run,
            requested_by=command.requested_by,
            tenant_id=tenant_id,
        )
        if isinstance(replay_candidate, ConsumerDlqReplayResult):
            return replay_candidate

        duplicate_result = await self._consumer_dlq_duplicate_replay_result(
            tenant_id=tenant_id,
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
        evidence_failure = replay_evidence_failure(replay_candidate.context)
        if evidence_failure is not None:
            return await self._consumer_dlq_missing_payload_result(
                event_id=event_id,
                correlation_id=event.correlation_id,
                replay_job_id=replay_candidate.job_id,
                context=replay_candidate.context,
                replay_fingerprint=replay_candidate.replay_fingerprint,
                evidence_failure=evidence_failure,
                dry_run=command.dry_run,
                requested_by=command.requested_by,
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

    async def _required_consumer_dlq_event(self, event_id: str, *, tenant_id: str) -> Any:
        event = await self.ingestion_job_service.get_consumer_dlq_event(
            event_id,
            tenant_id=tenant_id,
        )
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
        correlation_id: str | None,
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
        correlation_id: str | None,
        replay_job_id: str,
        context: Any | None,
        replay_fingerprint: str,
        evidence_failure: ReplayEvidenceFailure,
        dry_run: bool,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult:
        replay_reason = (
            "Correlated ingestion job durable replay evidence is not authorized: "
            f"{evidence_failure.value}."
        )
        return await self._record_consumer_dlq_replay_result(
            event_id=event_id,
            correlation_id=correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint if context else None,
            replay_fingerprint=replay_fingerprint,
            replay_status="not_replayable",
            dry_run=dry_run,
            replay_reason=replay_reason,
            message=replay_reason,
            requested_by=requested_by,
        )

    async def _consumer_dlq_replay_candidate_or_result(
        self,
        *,
        event_id: str,
        correlation_id: str | None,
        dry_run: bool,
        requested_by: str | None,
        tenant_id: str,
        ingestion_job_id: str | None = None,
    ) -> ConsumerDlqReplayCandidate | ConsumerDlqReplayResult:
        replay_job = await self._correlated_consumer_dlq_replay_job(
            correlation_id=correlation_id,
            ingestion_job_id=ingestion_job_id,
            tenant_id=tenant_id,
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
        context = await self.ingestion_job_service.get_job_replay_context(
            replay_job_id,
            tenant_id=tenant_id,
        )
        replay_fingerprint = self._consumer_dlq_replay_fingerprint(
            event_id=event_id,
            correlation_id=correlation_id,
            replay_job_id=replay_job_id,
            context=context,
        )
        evidence_failure = (
            ReplayEvidenceFailure.PAYLOAD_UNAVAILABLE
            if context is None
            else replay_evidence_failure(context)
        )
        if evidence_failure is not None:
            return await self._consumer_dlq_missing_payload_result(
                event_id=event_id,
                correlation_id=correlation_id,
                replay_job_id=replay_job_id,
                context=context,
                replay_fingerprint=replay_fingerprint,
                evidence_failure=evidence_failure,
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
        correlation_id: str | None,
        ingestion_job_id: str | None,
        tenant_id: str,
    ) -> Any | None:
        if ingestion_job_id is not None:
            replay_job = await self.ingestion_job_service.get_job(
                ingestion_job_id,
                tenant_id=tenant_id,
            )
            if replay_job is None or replay_job.status not in {"failed", "queued", "accepted"}:
                return None
            return replay_job
        if correlation_id is None:
            return None
        return await self.ingestion_job_service.get_unique_replayable_job_by_correlation_id(
            correlation_id,
            tenant_id=tenant_id,
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
        tenant_id: str,
        event_id: str,
        correlation_id: str | None,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        dry_run: bool,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult | None:
        existing_success = (
            await self.ingestion_job_service.find_successful_replay_audit_by_fingerprint(
                replay_fingerprint,
                tenant_id=tenant_id,
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
        correlation_id: str | None,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> None:
        try:
            with ingestion_job_scope(job_id):
                await self.replay_payload_dispatcher.replay_payload(
                    endpoint=context.endpoint,
                    payload=context.request_payload,
                    idempotency_key=context.idempotency_key,
                )
        except Exception as exc:
            failure_reason = project_ingestion_failure_evidence(
                failure_code="INGESTION_DLQ_REPLAY_FAILED",
                failure_detail=None,
                failure_headers=None,
            ).reason
            replay_audit_id = await self._record_mandatory_replay_audit(
                event_id=event_id,
                replay_fingerprint=replay_fingerprint,
                correlation_id=correlation_id,
                job_id=job_id,
                endpoint=context.endpoint,
                replay_status="failed",
                dry_run=False,
                replay_reason=failure_reason,
                requested_by=requested_by,
            )
            raise ReplayCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                {
                    "code": "INGESTION_DLQ_REPLAY_FAILED",
                    "message": failure_reason,
                    "replay_audit_id": replay_audit_id,
                },
            ) from exc

    async def _mark_consumer_dlq_replay_replayed(
        self,
        *,
        event_id: str,
        correlation_id: str | None,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> ConsumerDlqReplayResult:
        try:
            transitioned = await self.ingestion_job_service.mark_retried_and_queued(
                job_id,
                tenant_id=context.tenant_id,
            )
            if not transitioned:
                replay_audit_id = await self._record_mandatory_replay_audit(
                    event_id=event_id,
                    replay_fingerprint=replay_fingerprint,
                    correlation_id=correlation_id,
                    job_id=job_id,
                    endpoint=context.endpoint,
                    replay_status="replayed_bookkeeping_failed",
                    dry_run=False,
                    replay_reason=(
                        "Replay publish succeeded but ingestion job state transition was rejected."
                    ),
                    requested_by=requested_by,
                )
                raise ReplayCommandError(
                    HTTP_CONFLICT,
                    {
                        "code": "INGESTION_DLQ_REPLAY_BOOKKEEPING_CONFLICT",
                        "message": (
                            "Replay publish succeeded but ingestion job state changed before "
                            "bookkeeping completed."
                        ),
                        "replay_audit_id": replay_audit_id,
                        "replay_fingerprint": replay_fingerprint,
                    },
                )
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
            replay_reason = project_ingestion_failure_evidence(
                failure_code="INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED",
                failure_detail=None,
                failure_headers=None,
            ).reason
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
