from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionRetryRequest
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService

from .replay_command_errors import ReplayCommandError
from .replay_payload_dispatcher import ReplayPayloadDispatcher
from .replay_retry_payloads import (
    MissingReplayRecordKeysError,
    deterministic_replay_fingerprint,
    filter_payload_by_record_keys,
    payload_record_count,
)

logger = logging.getLogger(__name__)

HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_INTERNAL_SERVER_ERROR = 500

INGESTION_JOB_RETRY_RECOVERY_PATH = "ingestion_job_retry"

INGESTION_JOB_RETRY_REMEDIATIONS = {
    "not_found": "Verify the ingestion job id from the operations job list before retrying.",
    "retry_unsupported": (
        "Recover the source batch from upstream records; this job has no durable replay payload."
    ),
    "partial_retry_unsupported": (
        "Retry the full stored payload or use an endpoint with governed partial retry support."
    ),
    "partial_retry_records_not_found": (
        "Correct the requested record_keys against the stored replay payload before retrying."
    ),
    "retry_blocked": (
        "Resume ingestion operations mode or wait for the replay window to permit retries."
    ),
    "duplicate_blocked": (
        "Inspect the existing replay audit before forcing any manual recovery action."
    ),
    "publish_failed": (
        "Check ingestion publisher health and retry after the downstream publish path recovers."
    ),
    "bookkeeping_failed": (
        "Inspect replay audit state and job queue state before retrying or reconciling manually."
    ),
    "bookkeeping_conflict": (
        "Refresh the ingestion job status and replay audit before retrying; another recovery path "
        "changed the job state."
    ),
    "audit_write_failed": (
        "Do not assume replay completion; restore replay audit persistence and retry safely."
    ),
}


@dataclass(frozen=True)
class IngestionRetryCommandService:
    ingestion_job_service: IngestionJobService
    replay_payload_dispatcher: ReplayPayloadDispatcher

    async def retry_ingestion_job(
        self,
        *,
        job_id: str,
        retry_request: IngestionRetryRequest,
        requested_by: str | None,
    ) -> Any:
        context = await self._required_job_replay_context(job_id)
        replay_payload = self._retry_payload_or_error(
            context=context,
            retry_request=retry_request,
        )
        replay_record_count = payload_record_count(replay_payload)
        await self._assert_ingestion_retry_allowed(
            submitted_at=context.submitted_at,
            replay_record_count=replay_record_count,
        )
        replay_fingerprint = deterministic_replay_fingerprint(
            event_id=f"job:{job_id}",
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            payload=replay_payload,
            idempotency_key=context.idempotency_key,
        )

        if retry_request.dry_run:
            return await self._dry_run_ingestion_job_retry(
                job_id=job_id,
                context=context,
                replay_fingerprint=replay_fingerprint,
                requested_by=requested_by,
            )

        await self._block_duplicate_ingestion_job_retry(
            job_id=job_id,
            context=context,
            replay_fingerprint=replay_fingerprint,
            requested_by=requested_by,
        )
        await self._publish_ingestion_job_retry(
            job_id=job_id,
            context=context,
            retry_request=retry_request,
            replay_payload=replay_payload,
            replay_fingerprint=replay_fingerprint,
            requested_by=requested_by,
        )
        await self._mark_ingestion_job_retry_replayed(
            job_id=job_id,
            context=context,
            replay_fingerprint=replay_fingerprint,
            requested_by=requested_by,
        )
        return await self._required_job_after_retry(job_id)

    async def _required_job_replay_context(self, job_id: str) -> Any:
        context = await self.ingestion_job_service.get_job_replay_context(job_id)
        if context is None:
            raise ReplayCommandError(
                HTTP_NOT_FOUND,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_JOB_NOT_FOUND",
                    message=f"Ingestion job '{job_id}' was not found.",
                    outcome="not_found",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["not_found"],
                ),
            )
        if context.request_payload is None:
            raise ReplayCommandError(
                HTTP_CONFLICT,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_JOB_RETRY_UNSUPPORTED",
                    message=(
                        f"Ingestion job '{job_id}' does not have stored request payload and "
                        "cannot be retried."
                    ),
                    outcome="retry_unsupported",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["retry_unsupported"],
                ),
            )
        return context

    def _retry_payload_or_error(
        self,
        *,
        context: Any,
        retry_request: IngestionRetryRequest,
    ) -> dict[str, Any]:
        try:
            return filter_payload_by_record_keys(
                endpoint=context.endpoint,
                payload=context.request_payload,
                record_keys=retry_request.record_keys,
            )
        except MissingReplayRecordKeysError as exc:
            raise ReplayCommandError(
                HTTP_CONFLICT,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_PARTIAL_RETRY_RECORDS_NOT_FOUND",
                    message=str(exc),
                    outcome="partial_retry_records_not_found",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["partial_retry_records_not_found"],
                    missing_record_keys=exc.missing_record_keys,
                ),
            ) from exc
        except ValueError as exc:
            raise ReplayCommandError(
                HTTP_CONFLICT,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_PARTIAL_RETRY_UNSUPPORTED",
                    message=str(exc),
                    outcome="partial_retry_unsupported",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["partial_retry_unsupported"],
                ),
            ) from exc

    async def _assert_ingestion_retry_allowed(
        self,
        *,
        submitted_at: datetime,
        replay_record_count: int,
    ) -> None:
        try:
            await self.ingestion_job_service.assert_retry_allowed_for_records(
                submitted_at=submitted_at,
                replay_record_count=replay_record_count,
            )
        except PermissionError as exc:
            raise ReplayCommandError(
                HTTP_CONFLICT,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_RETRY_BLOCKED",
                    message=str(exc),
                    outcome="retry_blocked",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["retry_blocked"],
                ),
            ) from exc

    async def _dry_run_ingestion_job_retry(
        self,
        *,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> Any:
        await self._record_ingestion_job_retry_audit(
            job_id=job_id,
            context=context,
            replay_fingerprint=replay_fingerprint,
            replay_status="dry_run",
            dry_run=True,
            replay_reason="Dry-run successful. Ingestion job retry is replayable.",
            requested_by=requested_by,
        )
        job = await self.ingestion_job_service.get_job(job_id)
        if job is None:
            raise ReplayCommandError(
                HTTP_NOT_FOUND,
                {
                    "code": "INGESTION_JOB_NOT_FOUND",
                    "message": f"Ingestion job '{job_id}' was not found after dry-run.",
                },
            )
        return job

    async def _block_duplicate_ingestion_job_retry(
        self,
        *,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> None:
        existing_success = (
            await self.ingestion_job_service.find_successful_replay_audit_by_fingerprint(
                replay_fingerprint=replay_fingerprint,
                recovery_path="ingestion_job_retry",
            )
        )
        if existing_success:
            await self._record_ingestion_job_retry_audit(
                job_id=job_id,
                context=context,
                replay_fingerprint=replay_fingerprint,
                replay_status="duplicate_blocked",
                dry_run=False,
                replay_reason=(
                    "Retry blocked because this deterministic retry fingerprint was already "
                    f"replayed successfully (replay_id={existing_success['replay_id']})."
                ),
                requested_by=requested_by,
            )
            raise ReplayCommandError(
                HTTP_CONFLICT,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_RETRY_DUPLICATE_BLOCKED",
                    message=(
                        "Retry blocked because an equivalent deterministic replay already "
                        "succeeded."
                    ),
                    outcome="duplicate_blocked",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["duplicate_blocked"],
                    replay_fingerprint=replay_fingerprint,
                ),
            )

    async def _publish_ingestion_job_retry(
        self,
        *,
        job_id: str,
        context: Any,
        retry_request: IngestionRetryRequest,
        replay_payload: dict[str, Any],
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> None:
        try:
            await _replay_job_payload(
                endpoint=context.endpoint,
                payload=replay_payload,
                idempotency_key=context.idempotency_key,
                replay_payload_dispatcher=self.replay_payload_dispatcher,
            )
        except Exception as exc:
            replay_audit_id = await self._record_ingestion_job_retry_audit(
                job_id=job_id,
                context=context,
                replay_fingerprint=replay_fingerprint,
                replay_status="failed",
                dry_run=False,
                replay_reason=str(exc),
                requested_by=requested_by,
            )
            await self.ingestion_job_service.mark_failed(
                job_id,
                str(exc),
                failure_phase="retry_publish",
                failed_record_keys=retry_request.record_keys,
            )
            raise ReplayCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_RETRY_PUBLISH_FAILED",
                    message=(
                        "Ingestion job retry could not be published to the downstream ingestion "
                        "pipeline."
                    ),
                    outcome="publish_failed",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["publish_failed"],
                    replay_audit_id=replay_audit_id,
                    replay_fingerprint=replay_fingerprint,
                ),
            ) from exc

    async def _mark_ingestion_job_retry_replayed(
        self,
        *,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        requested_by: str | None,
    ) -> None:
        try:
            transitioned = await self.ingestion_job_service.mark_retried_and_queued(job_id)
            if not transitioned:
                replay_audit_id = await self._record_mandatory_replay_audit(
                    recovery_path="ingestion_job_retry",
                    event_id=f"job:{job_id}",
                    replay_fingerprint=replay_fingerprint,
                    correlation_id=None,
                    job_id=job_id,
                    endpoint=context.endpoint,
                    replay_status="replayed_bookkeeping_failed",
                    dry_run=False,
                    replay_reason=(
                        "Replay publish succeeded but ingestion job state transition was rejected."
                    ),
                    requested_by=requested_by,
                    correlation_missing_reason="ingestion_job_retry_uses_job_id",
                    alternate_lookup_key=f"job:{job_id}",
                )
                raise ReplayCommandError(
                    HTTP_CONFLICT,
                    ingestion_job_retry_problem_detail(
                        code="INGESTION_RETRY_BOOKKEEPING_CONFLICT",
                        message=(
                            "Replay publish succeeded but ingestion job state changed before "
                            "bookkeeping completed."
                        ),
                        outcome="bookkeeping_conflict",
                        remediation=INGESTION_JOB_RETRY_REMEDIATIONS["bookkeeping_conflict"],
                        replay_audit_id=replay_audit_id,
                        replay_fingerprint=replay_fingerprint,
                    ),
                )
            await self._record_ingestion_job_retry_audit(
                job_id=job_id,
                context=context,
                replay_fingerprint=replay_fingerprint,
                replay_status="replayed",
                dry_run=False,
                replay_reason="Ingestion job retry replay succeeded.",
                requested_by=requested_by,
            )
        except ReplayCommandError:
            raise
        except Exception as exc:
            replay_reason = f"Replay publish succeeded but post-publish bookkeeping failed: {exc}"
            replay_audit_id = await self._record_mandatory_replay_audit(
                recovery_path="ingestion_job_retry",
                event_id=f"job:{job_id}",
                replay_fingerprint=replay_fingerprint,
                correlation_id=None,
                job_id=job_id,
                endpoint=context.endpoint,
                replay_status="replayed_bookkeeping_failed",
                dry_run=False,
                replay_reason=replay_reason,
                requested_by=requested_by,
                correlation_missing_reason="ingestion_job_retry_uses_job_id",
                alternate_lookup_key=f"job:{job_id}",
            )
            raise ReplayCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_RETRY_BOOKKEEPING_FAILED",
                    message=(
                        "Replay publish succeeded but post-publish bookkeeping did not complete."
                    ),
                    outcome="bookkeeping_failed",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["bookkeeping_failed"],
                    replay_audit_id=replay_audit_id,
                    replay_fingerprint=replay_fingerprint,
                ),
            ) from exc

    async def _required_job_after_retry(self, job_id: str) -> Any:
        job = await self.ingestion_job_service.get_job(job_id)
        if job is None:
            raise ReplayCommandError(
                HTTP_NOT_FOUND,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_JOB_NOT_FOUND",
                    message=f"Ingestion job '{job_id}' was not found after retry.",
                    outcome="not_found",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["not_found"],
                ),
            )
        return job

    async def _record_ingestion_job_retry_audit(
        self,
        *,
        job_id: str,
        context: Any,
        replay_fingerprint: str,
        replay_status: str,
        dry_run: bool,
        replay_reason: str,
        requested_by: str | None,
    ) -> str:
        return await self._record_mandatory_replay_audit(
            recovery_path=INGESTION_JOB_RETRY_RECOVERY_PATH,
            event_id=f"job:{job_id}",
            replay_fingerprint=replay_fingerprint,
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            replay_status=replay_status,
            dry_run=dry_run,
            replay_reason=replay_reason,
            requested_by=requested_by,
            correlation_missing_reason="ingestion_job_retry_uses_job_id",
            alternate_lookup_key=f"job:{job_id}",
        )

    async def _record_mandatory_replay_audit(
        self,
        *,
        recovery_path: str,
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
                recovery_path=recovery_path,
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
                    "recovery_path": recovery_path,
                    "event_id": event_id,
                    "job_id": job_id,
                    "replay_status": replay_status,
                },
            )
            raise ReplayCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                ingestion_job_retry_problem_detail(
                    code="INGESTION_REPLAY_AUDIT_WRITE_FAILED",
                    message=(
                        "Replay audit could not be recorded; replay outcome was not acknowledged."
                    ),
                    outcome="audit_write_failed",
                    remediation=INGESTION_JOB_RETRY_REMEDIATIONS["audit_write_failed"],
                    recovery_path=recovery_path,
                    event_id=event_id,
                    job_id=job_id,
                    replay_status=replay_status,
                    replay_fingerprint=replay_fingerprint,
                ),
            ) from exc


async def _replay_job_payload(
    *,
    endpoint: str,
    payload: dict[str, Any],
    idempotency_key: str | None,
    replay_payload_dispatcher: ReplayPayloadDispatcher,
) -> None:
    await replay_payload_dispatcher.replay_payload(
        endpoint=endpoint,
        payload=payload,
        idempotency_key=idempotency_key,
    )


def ingestion_job_retry_problem_detail(
    *,
    code: str,
    message: str,
    outcome: str,
    remediation: str,
    **extra: Any,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "code": code,
        "message": message,
        "outcome": outcome,
        "remediation": remediation,
        "recovery_path": INGESTION_JOB_RETRY_RECOVERY_PATH,
    }
    detail.update(extra)
    return detail
