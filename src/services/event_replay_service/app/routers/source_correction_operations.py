"""Read-only completion projection under the existing operation owner."""

from time import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from portfolio_common.api_contract.async_commands import AsyncCommandStatus
from portfolio_common.command_authorization import (
    SOURCE_CORRECTION_CAPABILITY,
)
from portfolio_common.enterprise_readiness import (
    load_default_enterprise_settings,
    verify_service_principal,
)
from portfolio_common.enterprise_request_context import request_correlation_id

from ..dependencies import get_source_correction_operation_status
from ..infrastructure.source_correction_operation_status import (
    SourceCorrectionOperationNotFound,
    SqlAlchemySourceCorrectionOperationStatus,
)

router = APIRouter()


def _problem(status_code: int, code: str, message: str, correlation_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "correlation_id": correlation_id, "details": {}},
    )


@router.get(
    "/ingestion/jobs/{job_id}/source-correction",
    response_model=AsyncCommandStatus,
    tags=["Ingestion Operations"],
    summary="Read committed source-confirmation status",
    description=(
        "What: Project the result of one tenant-owned source-confirmation operation.\n"
        "How: Verify dedicated service authority; independently reload the operation, signed "
        "intent, immutable revision, original raw source and complete retained receipt. "
        "Only a fully bound durable revision is SUCCEEDED; accepted intent is QUEUED.\n"
        "When: Follow the ingestion command's status_url through the public gateway. "
        "This route is owned by event_replay_service, not by a new job engine."
    ),
    responses={
        403: {"description": "Verified dedicated correction authority absent."},
        404: {"description": "Tenant-owned correction operation was not found."},
        503: {"description": "Owning evidence store was unavailable."},
    },
)
async def read_source_correction_operation(
    request: Request,
    job_id: str = Path(
        min_length=1,
        max_length=128,
        description="Source-confirmation ingestion operation identifier.",
    ),
    status_reader: SqlAlchemySourceCorrectionOperationStatus = Depends(
        get_source_correction_operation_status
    ),
) -> AsyncCommandStatus | JSONResponse:
    correlation_id = request_correlation_id(request.headers) or str(uuid4())
    principal = verify_service_principal(
        dict(request.headers), load_default_enterprise_settings(service_name="event_replay_service")
    )
    tenant = request.headers.get("x-tenant-id", "").strip()
    if (
        isinstance(principal, str)
        or SOURCE_CORRECTION_CAPABILITY not in principal.capabilities
        or not tenant
    ):
        return _problem(
            403,
            "SOURCE_CORRECTION_GRANT_REQUIRED",
            "Verified source-confirmation authority is required.",
            correlation_id,
        )
    try:
        result = await status_reader.read(tenant_id=tenant, operation_id=job_id, now=int(time()))
        return result.model_copy(update={"correlation_id": correlation_id})
    except SourceCorrectionOperationNotFound:
        return _problem(
            404,
            "SOURCE_COMMAND_OPERATION_NOT_FOUND",
            "The source-confirmation operation was not found.",
            correlation_id,
        )
    except (RuntimeError, ValueError):
        return _problem(
            503,
            "SOURCE_COMMAND_OPERATION_UNAVAILABLE",
            "Source-confirmation operation authority is unavailable.",
            correlation_id,
        )
