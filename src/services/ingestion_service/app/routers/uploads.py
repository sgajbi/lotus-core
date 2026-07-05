import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from ..application.errors import ApplicationError
from ..application.upload_commands import (
    UploadCommitCommand,
    UploadCommitResult,
    UploadPreviewCommand,
    UploadPreviewResult,
)
from ..dependencies import get_ingestion_service, require_upload_adapter_enabled
from ..DTOs.upload_dto import (
    UploadCommitResponse,
    UploadEntityType,
    UploadPreviewResponse,
    UploadRowError,
)
from ..enterprise_readiness import authorize_capability, emit_audit_event
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from ..services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
)
from ..services.upload_ingestion_service import UploadIngestionService
from ..services.upload_publishers import IngestionServiceUploadPublisher
from ..services.upload_validation import (
    UPLOAD_PARSER_BUDGET_REASON_CODE,
    BulkUploadValidator,
    UploadParserBudget,
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
UPLOAD_MULTIPART_OVERHEAD_BYTES = 64 * 1024
UPLOAD_PREVIEW_SAMPLE_CAPABILITY = "ingestion.uploads.preview_samples.read"
UPLOAD_CSV_CONTENT_TYPES = frozenset(
    {
        "application/csv",
        "application/vnd.ms-excel",
        "text/csv",
        "text/plain",
    }
)
UPLOAD_XLSX_CONTENT_TYPES = frozenset(
    {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
)
HTTP_422_UNPROCESSABLE_CONTENT = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
UPLOAD_APPLICATION_ERROR_STATUS = {
    "unsupported_upload_file_format": status.HTTP_400_BAD_REQUEST,
    "invalid_csv_content": status.HTTP_400_BAD_REQUEST,
    "invalid_xlsx_content": status.HTTP_400_BAD_REQUEST,
    UPLOAD_PARSER_BUDGET_REASON_CODE: status.HTTP_413_CONTENT_TOO_LARGE,
    "empty_upload": status.HTTP_400_BAD_REQUEST,
    "upload_invalid_rows": HTTP_422_UNPROCESSABLE_CONTENT,
    "upload_no_valid_rows": HTTP_422_UNPROCESSABLE_CONTENT,
}

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
UPLOAD_CONTENT_TYPE_MISMATCH_EXAMPLE = {
    "detail": {
        "code": "INGESTION_UPLOAD_CONTENT_TYPE_MISMATCH",
        "message": "Upload content type does not match the file extension.",
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


def get_upload_ingestion_service(
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> UploadIngestionService:
    adapter_settings = get_ingestion_service_settings().adapter_mode
    return UploadIngestionService(
        validator=BulkUploadValidator(
            budget=UploadParserBudget(
                max_rows=adapter_settings.upload_max_rows,
                max_columns=adapter_settings.upload_max_columns,
                max_cell_length=adapter_settings.upload_max_cell_length,
            )
        ),
        publisher=IngestionServiceUploadPublisher(ingestion_service),
    )


def upload_application_error_to_http(exc: ApplicationError) -> HTTPException:
    return HTTPException(
        status_code=UPLOAD_APPLICATION_ERROR_STATUS.get(
            exc.reason_code,
            status.HTTP_400_BAD_REQUEST,
        ),
        detail=exc.detail,
    )


def upload_preview_command_from_api(
    *,
    entity_type: UploadEntityType,
    filename: str,
    content: bytes,
    sample_size: int,
    include_sample_rows: bool = False,
) -> UploadPreviewCommand:
    return UploadPreviewCommand(
        entity_type=entity_type,
        filename=filename,
        content=content,
        sample_size=sample_size,
        include_sample_rows=include_sample_rows,
    )


def upload_commit_command_from_api(
    *,
    entity_type: UploadEntityType,
    filename: str,
    content: bytes,
    allow_partial: bool,
) -> UploadCommitCommand:
    return UploadCommitCommand(
        entity_type=entity_type,
        filename=filename,
        content=content,
        allow_partial=allow_partial,
    )


def upload_preview_response_from_result(
    result: UploadPreviewResult,
) -> UploadPreviewResponse:
    return UploadPreviewResponse(
        entity_type=result.entity_type,
        file_format=result.file_format,
        total_rows=result.total_rows,
        valid_rows=result.valid_rows,
        invalid_rows=result.invalid_rows,
        sample_rows=result.sample_rows,
        errors=[
            UploadRowError(row_number=error.row_number, message=error.message)
            for error in result.errors
        ],
    )


def upload_commit_response_from_result(result: UploadCommitResult) -> UploadCommitResponse:
    return UploadCommitResponse(
        entity_type=result.entity_type,
        file_format=result.file_format,
        total_rows=result.total_rows,
        valid_rows=result.valid_rows,
        invalid_rows=result.invalid_rows,
        published_rows=result.published_rows,
        skipped_rows=result.skipped_rows,
        message=result.message,
    )


def _upload_format_from_filename(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        return "csv"
    if lowered.endswith(".xlsx"):
        return "xlsx"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported file format. Use .csv or .xlsx.",
    )


def _normalized_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _validate_upload_content_type(file: UploadFile) -> None:
    file_format = _upload_format_from_filename(file.filename or "upload.csv")
    content_type = _normalized_content_type(file.content_type)
    if not content_type or content_type == "application/octet-stream":
        return
    expected_types = UPLOAD_CSV_CONTENT_TYPES if file_format == "csv" else UPLOAD_XLSX_CONTENT_TYPES
    if content_type in expected_types:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "INGESTION_UPLOAD_CONTENT_TYPE_MISMATCH",
            "message": "Upload content type does not match the file extension.",
            "filename": file.filename,
            "content_type": content_type,
            "expected_file_format": file_format,
        },
    )


def _request_content_length(request: Request) -> int | None:
    raw_value = request.headers.get("content-length")
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value >= 0 else None


def _raise_upload_too_large(max_bytes: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={
            "code": "INGESTION_UPLOAD_TOO_LARGE",
            "message": "Bulk upload payload exceeds the configured byte limit.",
            "max_bytes": max_bytes,
        },
    )


async def _read_bounded_upload_content(
    file: UploadFile,
    *,
    content_length: int | None = None,
) -> bytes:
    max_bytes = get_ingestion_service_settings().adapter_mode.upload_max_bytes
    if content_length is not None and content_length > max_bytes + UPLOAD_MULTIPART_OVERHEAD_BYTES:
        _raise_upload_too_large(max_bytes)
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await file.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            _raise_upload_too_large(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


def _enforce_upload_rate_limit(endpoint: str) -> None:
    try:
        enforce_ingestion_write_rate_limit(endpoint=endpoint, record_count=1)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc


def _authorize_preview_sample_rows(request: Request) -> None:
    allowed, reason = authorize_capability(
        dict(request.headers),
        UPLOAD_PREVIEW_SAMPLE_CAPABILITY,
    )
    if not allowed:
        emit_audit_event(
            action="DENY POST /ingest/uploads/preview sample_rows",
            actor_id=request.headers.get("X-Actor-Id", "unknown"),
            tenant_id=request.headers.get("X-Tenant-Id", "default"),
            role=request.headers.get("X-Role", "unknown"),
            correlation_id=request.headers.get("X-Correlation-Id"),
            metadata={"reason": reason, "capability": UPLOAD_PREVIEW_SAMPLE_CAPABILITY},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INGESTION_UPLOAD_SAMPLE_ROWS_FORBIDDEN",
                "message": "Upload preview sample rows require a signed privileged capability.",
                "reason": reason,
                "capability": UPLOAD_PREVIEW_SAMPLE_CAPABILITY,
            },
        )
    emit_audit_event(
        action="POST /ingest/uploads/preview sample_rows",
        actor_id=request.headers.get("X-Actor-Id", "unknown"),
        tenant_id=request.headers.get("X-Tenant-Id", "default"),
        role=request.headers.get("X-Role", "unknown"),
        correlation_id=request.headers.get("X-Correlation-Id"),
        metadata={"capability": UPLOAD_PREVIEW_SAMPLE_CAPABILITY},
    )


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
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Preview parse-rate protection blocked the request.",
            "content": {"application/json": {"example": INGESTION_RATE_LIMIT_EXCEEDED_EXAMPLE}},
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
    request: Request,
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
        description="Maximum number of validation errors and privileged sample rows to include.",
        examples=[20],
    ),
    include_sample_rows: bool = Form(
        False,
        description=(
            "Return redacted valid sample rows. Requires the signed "
            "ingestion.uploads.preview_samples.read capability."
        ),
        examples=[False],
    ),
    _: None = Depends(require_upload_adapter_enabled),
    upload_service: UploadIngestionService = Depends(get_upload_ingestion_service),
):
    if include_sample_rows:
        _authorize_preview_sample_rows(request)
    _validate_upload_content_type(file)
    _enforce_upload_rate_limit("/ingest/uploads/preview")
    content = await _read_bounded_upload_content(
        file,
        content_length=_request_content_length(request),
    )
    try:
        result = upload_service.preview_upload(
            upload_preview_command_from_api(
                entity_type=entity_type,
                filename=file.filename or "upload.csv",
                content=content,
                sample_size=sample_size,
                include_sample_rows=include_sample_rows,
            )
        )
    except ApplicationError as exc:
        raise upload_application_error_to_http(exc) from exc
    response = upload_preview_response_from_result(result)
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
    request: Request,
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
    _validate_upload_content_type(file)
    _enforce_upload_rate_limit("/ingest/uploads/commit")
    content = await _read_bounded_upload_content(
        file,
        content_length=_request_content_length(request),
    )
    try:
        result = await upload_service.commit_upload(
            upload_commit_command_from_api(
                entity_type=entity_type,
                filename=file.filename or "upload.csv",
                content=content,
                allow_partial=allow_partial,
            )
        )
    except ApplicationError as exc:
        raise upload_application_error_to_http(exc) from exc
    except IngestionPublishError as exc:
        raise_ingestion_publish_unavailable(exc)
    response = upload_commit_response_from_result(result)
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
