"""Public ingestion boundary for fixed-income book-cost source authority."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import get_ingestion_publish_command_handler
from ..DTOs.fixed_income_book_cost_authority_dto import (
    FixedIncomeBookCostAuthorityIngestionRequest,
)
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..request_metadata import resolve_idempotency_key
from ..services.ingestion_publish_commands import (
    BatchPublishIngestionCommand,
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
)
from .publish_errors import (
    ingestion_idempotency_conflict_response,
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

router = APIRouter()

MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Failed to publish fixed-income book-cost authority.",
    failed_record_keys=[
        "TENANT_SG|BOOK_SG_PB|PORTFOLIO_001|BOND_001|LOT_001|CLEAN_COST_BASIS|"
        "accounting-policy-master|basis-001|v1"
    ],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)


@router.post(
    "/ingest/fixed-income-book-cost-authorities",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=MODE_BLOCKED_EXAMPLE,
            publish_failed_example=PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Fixed-Income Book Cost"],
    summary="Ingest fixed-income book-cost authority",
    description=(
        "What: Accept effective-dated, source-versioned policy assignment, clean-cost basis, "
        "contractual amortization schedule, and effective-yield authority for exact source lots.\n"
        "How: Validate strict financial contracts, reject duplicate source versions, enforce "
        "ingestion idempotency and write controls, then publish each record on the governed "
        "tenant/legal-book/portfolio/security/lot ordering key.\n"
        "When: Use when an accounting-policy or book-of-record source establishes or corrects "
        "premium, discount, or original-issue-discount book-cost evolution. Core never infers "
        "face amount, yield, schedule, or policy from position quantity or product name."
    ),
)
async def ingest_fixed_income_book_cost_authorities(
    request: FixedIncomeBookCostAuthorityIngestionRequest,
    http_request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
) -> BatchIngestionAcceptedResponse:
    authenticated_tenant_id = http_request.headers.get("X-Tenant-Id", "").strip()
    authority_tenant_ids = {
        authority.header.scope.tenant_id.strip() for authority in request.authorities
    }
    if not authenticated_tenant_id or authority_tenant_ids != {authenticated_tenant_id}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="authority tenant scope must match the authenticated tenant",
        )
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_fixed_income_book_cost_authorities(
            BatchPublishIngestionCommand(
                tenant_context=http_request.state.tenant_context,
                endpoint=str(http_request.url.path),
                entity_type="fixed_income_book_cost_authority",
                records=request.authorities,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message=(
                    "Fixed-income book-cost authority accepted for asynchronous processing."
                ),
            )
        )
    except IngestionPublishCommandError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        ) from exc
    except IngestionPublishUnavailable as exc:
        raise_ingestion_publish_unavailable(exc.publish_error, job_id=exc.job_id)
    except IngestionPublishBookkeepingFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.detail,
        ) from exc

    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
