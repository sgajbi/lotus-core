from __future__ import annotations

from src.services.ingestion_service.app.application.errors import (
    UnsupportedOperation,
    ValidationRejected,
)
from src.services.ingestion_service.app.application.upload_commands import (
    UploadCommitResult,
    UploadPreviewResult,
    UploadRowIssue,
)
from src.services.ingestion_service.app.routers.uploads import (
    upload_application_error_to_http,
    upload_commit_command_from_api,
    upload_commit_response_from_result,
    upload_preview_command_from_api,
    upload_preview_response_from_result,
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


def test_upload_preview_command_from_api_uses_application_command() -> None:
    command = upload_preview_command_from_api(
        entity_type="transactions",
        filename="transactions.csv",
        content=b"payload",
        sample_size=5,
    )

    assert command.entity_type == "transactions"
    assert command.filename == "transactions.csv"
    assert command.content == b"payload"
    assert command.sample_size == 5


def test_upload_commit_command_from_api_uses_application_command() -> None:
    command = upload_commit_command_from_api(
        entity_type="transactions",
        filename="transactions.csv",
        content=b"payload",
        allow_partial=True,
    )

    assert command.entity_type == "transactions"
    assert command.allow_partial is True


def test_upload_preview_response_from_result_preserves_api_contract() -> None:
    response = upload_preview_response_from_result(
        UploadPreviewResult(
            entity_type="transactions",
            file_format="csv",
            total_rows=2,
            valid_rows=1,
            invalid_rows=1,
            sample_rows=[{"transaction_id": "T1"}],
            errors=[UploadRowIssue(row_number=3, message="bad row")],
        )
    )

    assert response.model_dump() == {
        "entity_type": "transactions",
        "file_format": "csv",
        "total_rows": 2,
        "valid_rows": 1,
        "invalid_rows": 1,
        "sample_rows": [{"transaction_id": "T1"}],
        "errors": [{"row_number": 3, "message": "bad row"}],
    }


def test_upload_commit_response_from_result_preserves_api_contract() -> None:
    response = upload_commit_response_from_result(
        UploadCommitResult(
            entity_type="transactions",
            file_format="csv",
            total_rows=2,
            valid_rows=1,
            invalid_rows=1,
            published_rows=1,
            skipped_rows=1,
            message="Upload committed and queued for processing.",
        )
    )

    assert response.model_dump() == {
        "entity_type": "transactions",
        "file_format": "csv",
        "total_rows": 2,
        "valid_rows": 1,
        "invalid_rows": 1,
        "published_rows": 1,
        "skipped_rows": 1,
        "message": "Upload committed and queued for processing.",
    }
