"""Public ingestion boundary for source-owned corporate-action manifests."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import get_ingestion_publish_command_handler
from ..DTOs.corporate_action_manifest_dto import CorporateActionManifestIngestionRequest
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
    message="Failed to publish corporate-action manifest authority.",
    failed_record_keys=[
        "PB_SG_GLOBAL_BAL_001|transaction-group|CA-GROUP-001|CA-EVENT-001|v1|"
        "corporate-actions-master|CA-EVENT-001|revision-1"
    ],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)


@router.post(
    "/ingest/corporate-action-manifests",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=MODE_BLOCKED_EXAMPLE,
            publish_failed_example=PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Corporate Actions"],
    summary="Ingest corporate-action parent manifests",
    description=(
        "What: Accept source-owned, versioned corporate-action parent manifests with exact "
        "expected "
        "child membership, dependency edges, completion posture, tenant/legal-book scope, and "
        "immutable source evidence. How: Core publishes each parent stream in monotonic version "
        "order on the governed portfolio transaction-group key and validates authenticated tenant "
        "scope before acceptance. When: Use this boundary before sending governed child "
        "transactions; child financial effects remain parked until the current persisted manifest "
        "is complete and READY."
    ),
)
async def ingest_corporate_action_manifests(
    request: CorporateActionManifestIngestionRequest,
    http_request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
) -> BatchIngestionAcceptedResponse:
    authenticated_tenant_id = http_request.headers.get("X-Tenant-Id", "").strip()
    manifest_tenant_ids = {manifest.tenant_id for manifest in request.manifests}
    if not authenticated_tenant_id or manifest_tenant_ids != {authenticated_tenant_id}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="manifest tenant scope must match the authenticated tenant",
        )
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_corporate_action_manifests(
            BatchPublishIngestionCommand(
                tenant_context=http_request.state.tenant_context,
                endpoint=str(http_request.url.path),
                entity_type="corporate_action_manifest",
                records=request.manifests,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message=(
                    "Corporate-action manifests accepted for asynchronous processing."
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
