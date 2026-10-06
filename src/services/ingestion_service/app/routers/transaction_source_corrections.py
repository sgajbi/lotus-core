"""Always-authenticated asynchronous evidence-only transaction commands."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse
from portfolio_common.api_contract.async_commands import AsyncCommandAccepted
from portfolio_common.command_authorization import (
    SOURCE_CORRECTION_CAPABILITY,
    CommandAuthorizationRejected,
)
from portfolio_common.enterprise_readiness import (
    load_default_enterprise_settings,
    verify_service_principal,
)
from portfolio_common.enterprise_request_context import request_correlation_id
from portfolio_common.enterprise_tenant_admission import (
    TenantContextAdmissionError,
    resolve_enterprise_tenant_context,
)
from sqlalchemy.exc import SQLAlchemyError

from ..application.transaction_source_corrections import (
    SOURCE_CORRECTION_ENDPOINT,
    SourceCorrectionSubmission,
    SourceCorrectionSubmissionRejected,
    SubmitTransactionSourceCorrection,
)
from ..dependencies import get_transaction_source_correction_submitter
from ..DTOs.transaction_source_correction_dto import TransactionSourceCorrectionRequest
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import get_request_lineage, resolve_idempotency_key
from ..services.ingestion_job_lifecycle import IngestionIdempotencyConflictError

router = APIRouter()

_PROBLEM_MESSAGES = {
    "SOURCE_CORRECTION_GRANT_REQUIRED": "Verified source-confirmation authority is required.",
    "SOURCE_CORRECTION_IDEMPOTENCY_REQUIRED": "X-Idempotency-Key is required.",
    "INGESTION_IDEMPOTENCY_KEY_INVALID": "X-Idempotency-Key is invalid.",
    "INGESTION_RATE_LIMIT_EXCEEDED": "The ingestion write budget is exhausted.",
    "SOURCE_COMMAND_IDEMPOTENCY_CONFLICT": "The idempotency key conflicts with a prior request.",
    "SOURCE_COMMAND_PREVIOUSLY_FAILED": "The previous source-confirmation operation failed.",
    "SOURCE_COMMAND_TARGET_UNAVAILABLE": "The requested source authority was not found.",
    "SOURCE_COMMAND_RAW_UNAVAILABLE": "The requested source authority was not found.",
    "INGESTION_MODE_BLOCKS_WRITES": "The current operating mode does not allow this command.",
    "SOURCE_COMMAND_OPERATION_UNAVAILABLE": (
        "Source-confirmation operation authority is unavailable."
    ),
}


def _problem(
    request: Request, status_code: int, code: str, *, idempotency_key: str | None = None
) -> JSONResponse:
    if code not in _PROBLEM_MESSAGES:
        code = "SOURCE_COMMAND_OPERATION_UNAVAILABLE"
    details = (
        {
            "idempotency_scope": "tenant-and-resource:transaction-source-evidence",
            "conflict_reason": "payload_fingerprint_mismatch",
        }
        if code == "SOURCE_COMMAND_IDEMPOTENCY_CONFLICT"
        else {}
    )
    content: dict[str, object] = {
        "code": code,
        "message": _PROBLEM_MESSAGES[code],
        "correlation_id": request_correlation_id(request.headers) or str(uuid4()),
        "details": details,
    }
    if code == "SOURCE_COMMAND_IDEMPOTENCY_CONFLICT" and idempotency_key is not None:
        # Echo only this admitted request's key, never the store's tenant-scoped key or payload.
        content["idempotency_key"] = idempotency_key
    return JSONResponse(status_code=status_code, content=content)


def _verified_submission(
    request: Request, transaction_id: str, body: TransactionSourceCorrectionRequest
) -> SourceCorrectionSubmission:
    headers = dict(request.headers)
    principal = verify_service_principal(
        headers, load_default_enterprise_settings(service_name="ingestion_service")
    )
    if isinstance(principal, str) or SOURCE_CORRECTION_CAPABILITY not in principal.capabilities:
        raise HTTPException(403, detail={"code": "SOURCE_CORRECTION_GRANT_REQUIRED"})
    try:
        context = resolve_enterprise_tenant_context(
            tenant_id=headers.get("x-tenant-id"),
            actor_id=headers.get("x-actor-id"),
            role=headers.get("x-role"),
            service_identity=principal.service_identity,
            correlation_id=headers.get("x-correlation-id"),
            identity_verified=True,
        )
    except TenantContextAdmissionError:
        raise HTTPException(403, detail={"code": "SOURCE_CORRECTION_GRANT_REQUIRED"}) from None
    key = resolve_idempotency_key(request)
    if key is None:
        raise HTTPException(400, detail={"code": "SOURCE_CORRECTION_IDEMPOTENCY_REQUIRED"})
    correlation, request_id, trace = get_request_lineage()
    correlation = context.correlation_id
    if not correlation or not context.actor_id:
        raise HTTPException(403, detail={"code": "SOURCE_CORRECTION_GRANT_REQUIRED"})
    return SourceCorrectionSubmission(
        transaction_id,
        body,
        context,
        principal,
        key,
        correlation,
        request_id or str(uuid4()),
        trace or correlation,
    )


@router.post(
    "/ingest/transactions/{transaction_id}/source-evidence",
    status_code=202,
    response_model=AsyncCommandAccepted,
    tags=["Transactions"],
    summary="Confirm missing transaction FX source evidence",
    description=(
        "What: Queue a missing-FX-source confirmation for an existing transaction.\n"
        "How: Verify dedicated service authority and persisted tenant ownership, bind the "
        "expected evidence head and exact body, then commit an operation and signed outbox "
        "command atomically. No economic transaction is rewritten or replayed.\n"
        "When: Use only to confirm a server-proven absent source as explicit zero; 202 is "
        "queued intent, not successful correction or qualification. Follow status_url."
    ),
    responses={
        400: {"description": "Closed input or required idempotency key was invalid."},
        403: {"description": "Verified dedicated correction authority was absent."},
        404: {"description": "Tenant-owned original source was unavailable."},
        409: {"description": "Idempotency conflict or previous failed operation."},
        429: {"description": "Native ingestion write rate protection refused the command."},
        503: {"description": "Native operating mode or operation store was unavailable."},
    },
)
async def submit_source_correction(
    body: TransactionSourceCorrectionRequest,
    request: Request,
    response: Response,
    transaction_id: str = Path(
        min_length=1, max_length=256, description="Existing canonical transaction identifier."
    ),
    submitter: SubmitTransactionSourceCorrection = Depends(
        get_transaction_source_correction_submitter
    ),
) -> AsyncCommandAccepted | JSONResponse:
    try:
        submission = _verified_submission(request, transaction_id, body)
    except HTTPException as exc:
        code = exc.detail.get("code", "") if isinstance(exc.detail, dict) else ""
        return _problem(request, exc.status_code, code)
    try:
        enforce_ingestion_write_rate_limit(endpoint=SOURCE_CORRECTION_ENDPOINT, record_count=1)
    except PermissionError:
        return _problem(request, 429, "INGESTION_RATE_LIMIT_EXCEEDED")
    try:
        result = await submitter.submit(submission)
    except CommandAuthorizationRejected:
        return _problem(request, 403, "SOURCE_CORRECTION_GRANT_REQUIRED")
    except IngestionIdempotencyConflictError:
        return _problem(
            request,
            409,
            "SOURCE_COMMAND_IDEMPOTENCY_CONFLICT",
            idempotency_key=submission.idempotency_key,
        )
    except SourceCorrectionSubmissionRejected as exc:
        unavailable = str(exc) in {
            "SOURCE_COMMAND_TARGET_UNAVAILABLE",
            "SOURCE_COMMAND_RAW_UNAVAILABLE",
        }
        return _problem(request, 404 if unavailable else 409, str(exc))
    except PermissionError:
        return _problem(request, 503, "INGESTION_MODE_BLOCKS_WRITES")
    except (SQLAlchemyError, RuntimeError):
        return _problem(request, 503, "SOURCE_COMMAND_OPERATION_UNAVAILABLE")
    response.headers["Location"] = result.status_url
    response.headers["Retry-After"] = str(result.retry_after_seconds)
    return result.model_copy(update={"correlation_id": submission.correlation_id})
