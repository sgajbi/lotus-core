from __future__ import annotations

from time import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)
from starlette.requests import Request

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
    UPLOAD_PREVIEW_SAMPLE_CAPABILITY,
    _authorize_preview_sample_rows,
    upload_application_error_to_http,
    upload_commit_command_from_api,
    upload_commit_response_from_result,
    upload_preview_command_from_api,
    upload_preview_response_from_result,
)


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/uploads/preview",
            "headers": [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in headers.items()
            ],
        }
    )


def _signed_enterprise_headers(capabilities: str) -> dict[str, str]:
    headers = {
        "X-Actor-Id": "actor-1",
        "X-Tenant-Id": "tenant-1",
        "X-Role": "ops",
        "X-Correlation-Id": "corr-1",
        "X-Service-Identity": "lotus-gateway",
        "X-Capabilities": capabilities,
        "X-Enterprise-Auth-Key-Id": "kms-key-1",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers),
        "auth-context-secret",
    )
    return headers


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
        include_sample_rows=True,
    )

    assert command.entity_type == "transactions"
    assert command.filename == "transactions.csv"
    assert command.content == b"payload"
    assert command.sample_size == 5
    assert command.include_sample_rows is True


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

    assert response.model_dump(exclude_none=True) == {
        "entity_type": "transactions",
        "file_format": "csv",
        "total_rows": 2,
        "valid_rows": 1,
        "invalid_rows": 1,
        "sample_rows": [{"transaction_id": "T1"}],
        "errors": [
            {
                "row_number": 3,
                "message": "bad row",
                "code": "SCHEMA_VALIDATION_FAILED",
                "severity": "error",
                "source_lineage": {},
            }
        ],
    }


def test_authorize_preview_sample_rows_requires_signed_capability(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")
    headers = _signed_enterprise_headers("ingestion.uploads.write")

    with pytest.raises(HTTPException) as exc_info:
        _authorize_preview_sample_rows(_request(headers))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["capability"] == UPLOAD_PREVIEW_SAMPLE_CAPABILITY


def test_authorize_preview_sample_rows_audits_signed_capability(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")
    headers = _signed_enterprise_headers(UPLOAD_PREVIEW_SAMPLE_CAPABILITY)

    with patch("src.services.ingestion_service.app.routers.uploads.emit_audit_event") as audit:
        _authorize_preview_sample_rows(_request(headers))

    assert audit.call_args.kwargs["metadata"]["capability"] == UPLOAD_PREVIEW_SAMPLE_CAPABILITY


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
