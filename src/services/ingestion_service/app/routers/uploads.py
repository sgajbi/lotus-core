import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ..adapter_mode import require_upload_adapter_enabled
from ..DTOs.upload_dto import UploadCommitResponse, UploadEntityType, UploadPreviewResponse
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from ..services.ingestion_service import IngestionPublishError
from ..services.upload_ingestion_service import (
    UploadIngestionService,
    get_upload_ingestion_service,
)
from ..settings import get_ingestion_service_settings
from .publish_errors import (
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter()
UPLOAD_READ_CHUNK_BYTES = 64 * 1024

UPLOAD_INVALID_EXAMPLE = {"detail": "Unsupported upload file format. Expected CSV or XLSX."}
UPLOAD_ADAPTER_DISABLED_EXAMPLE = {
    "detail": "Bulk upload adapter mode is disabled in this environment."
}
UPLOAD_TOO_LARGE_EXAMPLE = {
    "detail": {
        "code": "INGESTION_UPLOAD_TOO_LARGE",
        "message": "Bulk upload payload exceeds the configured byte limit.",
        "max_bytes": 5242880,
    }
}
INGESTION_MODE_BLOCKS_WRITES_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
INGESTION_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/uploads/commit.",
    }
}
UPLOAD_COMMIT_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message=(
        "Failed to publish transaction 'T2' after 1 earlier record(s) were already "
        "published. Remaining unpublished record keys: T2."
    ),
    failed_record_keys=["T2"],
    published_record_count=1,
)


async def _read_bounded_upload_content(file: UploadFile) -> bytes:
    max_bytes = get_ingestion_service_settings().adapter_mode.upload_max_bytes
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await file.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "INGESTION_UPLOAD_TOO_LARGE",
                    "message": "Bulk upload payload exceeds the configured byte limit.",
                    "max_bytes": max_bytes,
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/ingest/uploads/preview",
    response_model=UploadPreviewResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid upload file format or content.",
            "content": {"application/json": {"example": UPLOAD_INVALID_EXAMPLE}},
        },
        status.HTTP_410_GONE: {
            "description": "Bulk upload adapter mode disabled for this environment.",
            "content": {"application/json": {"example": UPLOAD_ADAPTER_DISABLED_EXAMPLE}},
        },
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "description": "Upload payload exceeds the configured byte limit.",
            "content": {"application/json": {"example": UPLOAD_TOO_LARGE_EXAMPLE}},
        },
    },
    tags=["Bulk Uploads"],
    summary="Preview and validate bulk upload data",
    description=(
        "What: Validate CSV/XLSX ingestion payloads without publishing records.\n"
        "How: Parse file rows, apply entity-specific schema checks, "
        "and return row-level validation feedback.\n"
        "When: Use before commit to catch data-quality issues in bulk adapter uploads."
    ),
)
async def preview_upload(
    entity_type: UploadEntityType = Form(
        ...,
        description="Entity family expected in the uploaded file.",
        examples=["portfolios"],
    ),
    file: UploadFile = File(
        ...,
        description="CSV or XLSX file containing rows for the selected upload entity family.",
        examples=["transactions.csv"],
    ),
    sample_size: int = Form(
        20,
        ge=1,
        le=100,
        description="Maximum number of valid normalized sample rows to include in the preview.",
        examples=[20],
    ),
    _: None = Depends(require_upload_adapter_enabled),
    upload_service: UploadIngestionService = Depends(get_upload_ingestion_service),
):
    content = await _read_bounded_upload_content(file)
    response = upload_service.preview_upload(
        entity_type=entity_type,
        filename=file.filename or "upload.csv",
        content=content,
        sample_size=sample_size,
    )
    logger.info(
        "Upload preview completed.",
        extra={
            "entity_type": entity_type,
            "upload_filename": file.filename,
            "total_rows": response.total_rows,
            "valid_rows": response.valid_rows,
            "invalid_rows": response.invalid_rows,
        },
    )
    return response


@router.post(
    "/ingest/uploads/commit",
    response_model=UploadCommitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid upload file format or content.",
            "content": {"application/json": {"example": UPLOAD_INVALID_EXAMPLE}},
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the commit request.",
            "content": {"application/json": {"example": INGESTION_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=INGESTION_MODE_BLOCKS_WRITES_EXAMPLE,
            publish_failed_example=UPLOAD_COMMIT_PUBLISH_FAILED_EXAMPLE,
        ),
        status.HTTP_410_GONE: {
            "description": "Bulk upload adapter mode disabled for this environment.",
            "content": {"application/json": {"example": UPLOAD_ADAPTER_DISABLED_EXAMPLE}},
        },
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "description": "Upload payload exceeds the configured byte limit.",
            "content": {"application/json": {"example": UPLOAD_TOO_LARGE_EXAMPLE}},
        },
    },
    tags=["Bulk Uploads"],
    summary="Commit validated bulk upload data",
    description=(
        "What: Commit CSV/XLSX data into canonical ingestion topics.\n"
        "How: Validate rows, enforce mode controls, and publish valid records "
        "(optionally partial when allow_partial=true).\n"
        "When: Use after preview passes for adapter-mode bulk ingestion."
    ),
)
async def commit_upload(
    entity_type: UploadEntityType = Form(
        ...,
        description="Entity family expected in the uploaded file.",
        examples=["transactions"],
    ),
    file: UploadFile = File(
        ...,
        description="CSV or XLSX file containing rows to validate and commit.",
        examples=["transactions.csv"],
    ),
    allow_partial: bool = Form(
        False,
        description="Allow valid rows to publish even when some rows fail validation.",
        examples=[False],
    ),
    _: None = Depends(require_upload_adapter_enabled),
    upload_service: UploadIngestionService = Depends(get_upload_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    content = await _read_bounded_upload_content(file)
    try:
        enforce_ingestion_write_rate_limit(
            endpoint="/ingest/uploads/commit",
            record_count=max(1, content.count(b"\n")),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    try:
        response = await upload_service.commit_upload(
            entity_type=entity_type,
            filename=file.filename or "upload.csv",
            content=content,
            allow_partial=allow_partial,
        )
    except IngestionPublishError as exc:
        raise_ingestion_publish_unavailable(exc)
    logger.info(
        "Upload commit completed.",
        extra={
            "entity_type": entity_type,
            "upload_filename": file.filename,
            "published_rows": response.published_rows,
            "skipped_rows": response.skipped_rows,
        },
    )
    return response
