"""Submit source-only intent through the existing ingestion operation owner."""

from collections.abc import Callable
from dataclasses import dataclass

from portfolio_common.api_contract.async_commands import (
    AsyncCommandAccepted,
    AsyncCommandIdempotency,
    SourceEvidenceConfirmationInput,
)
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal

from ..ports.transaction_source_operations import SourceCorrectionOperationOwner
from ..request_metadata import create_ingestion_job_id

SOURCE_CORRECTION_ENDPOINT = "/ingest/transactions/{transaction_id}/source-evidence"
SOURCE_CORRECTION_ENTITY = "transaction_source_correction"


class SourceCorrectionSubmissionRejected(ValueError):
    """Only bounded source-safe refusal codes may cross the HTTP boundary."""


@dataclass(frozen=True, slots=True)
class SourceCorrectionSubmission:
    target_transaction_id: str
    body: SourceEvidenceConfirmationInput
    tenant_context: TenantContext
    principal: VerifiedServicePrincipal
    idempotency_key: str
    correlation_id: str
    request_id: str
    trace_id: str


class SubmitTransactionSourceCorrection:
    def __init__(
        self,
        service_factory: Callable[[SourceCorrectionSubmission], SourceCorrectionOperationOwner],
    ) -> None:
        self._service_factory = service_factory

    async def submit(self, submission: SourceCorrectionSubmission) -> AsyncCommandAccepted:
        service = self._service_factory(submission)
        await service.assert_ingestion_writable()
        result = await service.create_or_get_job(
            job_id=create_ingestion_job_id(),
            endpoint=SOURCE_CORRECTION_ENDPOINT,
            entity_type=SOURCE_CORRECTION_ENTITY,
            accepted_count=1,
            idempotency_key=submission.idempotency_key,
            correlation_id=submission.correlation_id,
            request_id=submission.request_id,
            trace_id=submission.trace_id,
            tenant_context=submission.tenant_context,
            request_payload={
                "canonical_request_sha256": submission.body.canonical_request_sha256(
                    target_transaction_id=submission.target_transaction_id
                )
            },
        )
        job = result.job
        if job.status not in {"accepted", "queued"}:
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_PREVIOUSLY_FAILED")
        if not job.idempotency_key_reference:
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_OPERATION_UNAVAILABLE")
        return AsyncCommandAccepted(
            correlation_id=submission.correlation_id,
            operation_id=job.job_id,
            status_url=f"/ingestion/jobs/{job.job_id}/source-correction",
            idempotency=AsyncCommandIdempotency(
                key=job.idempotency_key_reference,
                scope="tenant-and-resource:transaction-source-evidence",
            ),
        )
