from __future__ import annotations

from src.services.ingestion_service.app.application.errors import (
    UnsupportedOperation,
    ValidationRejected,
)
from src.services.ingestion_service.app.routers.uploads import (
    upload_application_error_to_http,
)


def test_upload_application_error_to_http_maps_unsupported_format() -> None:
    http_error = upload_application_error_to_http(
        UnsupportedOperation(
            reason_code="unsupported_upload_file_format",
            detail="Unsupported file format. Use .csv or .xlsx.",
        )
    )

    assert http_error.status_code == 400
    assert http_error.detail == "Unsupported file format. Use .csv or .xlsx."


def test_upload_application_error_to_http_preserves_validation_detail() -> None:
    detail = {
        "message": "Upload contains invalid rows. Fix errors or use allow_partial=true.",
        "errors": [{"row_number": 2, "message": "transaction_date: invalid"}],
    }

    http_error = upload_application_error_to_http(
        ValidationRejected(reason_code="upload_invalid_rows", detail=detail)
    )

    assert http_error.status_code == 422
    assert http_error.detail == detail
