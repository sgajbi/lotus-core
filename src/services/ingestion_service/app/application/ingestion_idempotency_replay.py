from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

SAFE_PREVIOUS_FAILURE_MESSAGE = "The previous ingestion attempt failed."


class IngestionIdempotencyReplayDisposition(StrEnum):
    ACCEPTED = "accepted"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"


class IngestionIdempotencyReplayJob(Protocol):
    job_id: str
    status: str
    failure_reason: str | None
    failure_status_code: int | None
    failure_code: str | None
    failure_detail: dict[str, Any] | None
    failure_headers: dict[str, str] | None


@dataclass(frozen=True, slots=True)
class IngestionIdempotencyReplayResolution:
    disposition: IngestionIdempotencyReplayDisposition
    status_code: int | None = None
    detail: dict[str, Any] | None = None
    headers: dict[str, str] | None = None

    @property
    def accepted(self) -> bool:
        return self.disposition is IngestionIdempotencyReplayDisposition.ACCEPTED


def resolve_ingestion_idempotency_replay(
    job: IngestionIdempotencyReplayJob,
) -> IngestionIdempotencyReplayResolution:
    """Resolve an existing ingestion job without inferring success from existence alone."""

    failure_status_code = getattr(job, "failure_status_code", None)
    failure_code = getattr(job, "failure_code", None)
    if failure_status_code is not None or failure_code is not None:
        return _durable_failure_resolution(
            job=job,
            failure_status_code=failure_status_code,
            failure_code=failure_code,
        )

    if job.status == "queued":
        return IngestionIdempotencyReplayResolution(
            disposition=IngestionIdempotencyReplayDisposition.ACCEPTED,
        )

    if job.status == "failed":
        return IngestionIdempotencyReplayResolution(
            disposition=IngestionIdempotencyReplayDisposition.FAILED,
            status_code=500,
            detail={
                "code": "INGESTION_PREVIOUS_ATTEMPT_FAILED",
                "message": SAFE_PREVIOUS_FAILURE_MESSAGE,
                "job_id": job.job_id,
            },
        )

    if job.status == "accepted":
        return IngestionIdempotencyReplayResolution(
            disposition=IngestionIdempotencyReplayDisposition.IN_PROGRESS,
            status_code=409,
            detail={
                "code": "INGESTION_REQUEST_IN_PROGRESS",
                "message": "The original ingestion request has not reached a replay-safe state.",
                "job_id": job.job_id,
                "status": job.status,
            },
        )

    return IngestionIdempotencyReplayResolution(
        disposition=IngestionIdempotencyReplayDisposition.FAILED,
        status_code=500,
        detail={
            "code": "INGESTION_REPLAY_STATE_INVALID",
            "message": "The stored ingestion job state is not recognized.",
            "job_id": job.job_id,
            "status": job.status,
        },
    )


def _durable_failure_resolution(
    *,
    job: IngestionIdempotencyReplayJob,
    failure_status_code: int | None,
    failure_code: str | None,
) -> IngestionIdempotencyReplayResolution:
    status_code = failure_status_code if failure_status_code is not None else 500
    code = failure_code or "INGESTION_PREVIOUS_ATTEMPT_FAILED"
    stored_detail = getattr(job, "failure_detail", None)
    detail = dict(stored_detail) if stored_detail is not None else {}
    detail["code"] = code
    detail.setdefault("message", SAFE_PREVIOUS_FAILURE_MESSAGE)
    detail["job_id"] = job.job_id
    stored_headers = getattr(job, "failure_headers", None)
    return IngestionIdempotencyReplayResolution(
        disposition=IngestionIdempotencyReplayDisposition.FAILED,
        status_code=status_code,
        detail=detail,
        headers=dict(stored_headers) if stored_headers is not None else None,
    )
