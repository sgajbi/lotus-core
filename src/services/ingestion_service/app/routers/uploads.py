import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ..adapter_mode import require_upload_adapter_enabled
from ..DTOs.upload_dto import UploadCommitResponse, UploadEntityType, UploadPreviewResponse
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from ..services.upload_ingestion_service import (
    UploadIngestionService,
    get_upload_ingestion_service,
)

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_INVALID_EXAMPLE = {"detail": "Unsupported upload file format. Expected CSV or XLSX."}
UPLOAD_ADAPTER_DISABLED_EXAMPLE = {
    "detail": "Bulk upload adapter mode is disabled in this environment."
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
    content = await file.read()
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
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {"application/json": {"example": INGESTION_MODE_BLOCKS_WRITES_EXAMPLE}},
        },
        status.HTTP_410_GONE: {
            "description": "Bulk upload adapter mode disabled for this environment.",
            "content": {"application/json": {"example": UPLOAD_ADAPTER_DISABLED_EXAMPLE}},
        },
    },
    tags=["Bulk Uploads"],
    summary="Commit validated bulk upload data",
    description=(
        "What: Commit CSV/XLSX data into canonical ingestion topics.\n"
        "How: Validate rows, enforce mode controls, and publish valid records "
        "(optionally partial when allowPartial=true).\n"
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
    content = await file.read()
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
    response = await upload_service.commit_upload(
        entity_type=entity_type,
        filename=file.filename or "upload.csv",
        content=content,
        allow_partial=allow_partial,
    )
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
