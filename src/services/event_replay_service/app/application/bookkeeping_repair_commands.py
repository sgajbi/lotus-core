from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from src.services.ingestion_service.app.bookkeeping_recovery import (
    POST_BOOKKEEPING_FAILURE_PHASES,
    POST_BOOKKEEPING_REPAIR_ACTION,
    bookkeeping_reason_code,
)
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService

logger = logging.getLogger(__name__)

HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_INTERNAL_SERVER_ERROR = 500


class BookkeepingRepairCommandError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(
            str(detail.get("message", detail.get("code", "bookkeeping repair failed")))
        )
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class BookkeepingRepairResult:
    job_id: str
    previous_status: str
    repaired_status: str
    recovery_action: str
    supportability_reason_code: str
    retry_safe: bool
    message: str

    def to_response_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BookkeepingRepairCommandService:
    ingestion_job_service: IngestionJobService

    async def repair_ingestion_job_bookkeeping(self, job_id: str) -> BookkeepingRepairResult:
        job = await self._required_ingestion_job_for_bookkeeping_repair(job_id)
        previous_status = str(_job_field(job, "status"))
        failures = await self.ingestion_job_service.list_failures(job_id=job_id, limit=25)
        bookkeeping_phase = self._bookkeeping_repair_phase_or_error(
            failures=failures,
            job_id=job_id,
            previous_status=previous_status,
        )
        if previous_status == "accepted":
            await self._mark_ingestion_job_queued_for_bookkeeping_repair(
                job_id=job_id,
                previous_status=previous_status,
            )
        repaired = await self.ingestion_job_service.get_job(job_id)
        repaired_status = str(_job_field(repaired or job, "status"))
        return self._bookkeeping_repair_result(
            job_id=job_id,
            previous_status=previous_status,
            repaired_status=repaired_status,
            bookkeeping_phase=bookkeeping_phase,
        )

    async def _required_ingestion_job_for_bookkeeping_repair(self, job_id: str) -> Any:
        job = await self.ingestion_job_service.get_job(job_id)
        if job is None:
            raise BookkeepingRepairCommandError(
                HTTP_NOT_FOUND,
                {
                    "code": "INGESTION_JOB_NOT_FOUND",
                    "message": f"Ingestion job '{job_id}' was not found.",
                },
            )
        return job

    def _bookkeeping_repair_phase_or_error(
        self,
        *,
        failures: list[Any],
        job_id: str,
        previous_status: str,
    ) -> str:
        bookkeeping_phase = _first_bookkeeping_failure_phase(failures)
        if bookkeeping_phase is None or previous_status not in {"accepted", "queued"}:
            raise BookkeepingRepairCommandError(
                HTTP_CONFLICT,
                {
                    "code": "INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE",
                    "message": "Ingestion job is not eligible for bookkeeping repair.",
                    "job_id": job_id,
                    "status": previous_status,
                },
            )
        return bookkeeping_phase

    async def _mark_ingestion_job_queued_for_bookkeeping_repair(
        self,
        *,
        job_id: str,
        previous_status: str,
    ) -> None:
        try:
            await self.ingestion_job_service.mark_queued(job_id)
        except Exception as exc:
            logger.exception(
                "Ingestion bookkeeping repair failed.",
                extra={"job_id": job_id, "previous_status": previous_status},
            )
            raise BookkeepingRepairCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                {
                    "code": "INGESTION_BOOKKEEPING_REPAIR_FAILED",
                    "message": "Ingestion job bookkeeping repair did not complete.",
                    "job_id": job_id,
                    "recovery_action": POST_BOOKKEEPING_REPAIR_ACTION,
                },
            ) from exc

    @staticmethod
    def _bookkeeping_repair_result(
        *,
        job_id: str,
        previous_status: str,
        repaired_status: str,
        bookkeeping_phase: str,
    ) -> BookkeepingRepairResult:
        return BookkeepingRepairResult(
            job_id=job_id,
            previous_status=previous_status,
            repaired_status=repaired_status,
            recovery_action=POST_BOOKKEEPING_REPAIR_ACTION,
            supportability_reason_code=bookkeeping_reason_code(bookkeeping_phase),
            retry_safe=False,
            message=(
                f"Ingestion job bookkeeping repaired from {previous_status} to {repaired_status}."
            ),
        )


def _first_bookkeeping_failure_phase(failures: list[Any]) -> str | None:
    for failure in failures:
        failure_phase = _job_field(failure, "failure_phase")
        if failure_phase in POST_BOOKKEEPING_FAILURE_PHASES:
            return str(failure_phase)
    return None


def _job_field(job: Any, field: str) -> Any:
    if isinstance(job, dict):
        return job.get(field)
    return getattr(job, field, None)
