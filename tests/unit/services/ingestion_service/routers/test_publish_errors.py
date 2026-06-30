from __future__ import annotations

import pytest
from fastapi import HTTPException
from portfolio_common.logging_utils import (
    correlation_id_var,
    request_id_var,
    trace_id_var,
)

from src.services.ingestion_service.app.routers.publish_errors import (
    ingestion_publish_failed_detail,
    raise_ingestion_publish_unavailable,
)
from src.services.ingestion_service.app.services.ingestion_service import IngestionPublishError


def test_ingestion_publish_failed_detail_includes_dependency_retry_and_lineage() -> None:
    correlation_token = correlation_id_var.set("ING:corr-001")
    request_token = request_id_var.set("REQ:req-001")
    trace_token = trace_id_var.set("trace-001")
    try:
        detail = ingestion_publish_failed_detail(
            IngestionPublishError(
                "Failed to publish transaction 'T2'.",
                failed_record_keys=["T2", "T3"],
                published_record_count=1,
            ),
            job_id="job_001",
        )
    finally:
        correlation_id_var.reset(correlation_token)
        request_id_var.reset(request_token)
        trace_id_var.reset(trace_token)

    assert detail == {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Failed to publish transaction 'T2'.",
        "dependency": "kafka",
        "retryable": True,
        "retry_after_seconds": 30,
        "publish_state": "partial",
        "published_record_count": 1,
        "failed_record_keys": ["T2", "T3"],
        "job_id": "job_001",
        "correlation_id": "ING:corr-001",
        "request_id": "REQ:req-001",
        "trace_id": "trace-001",
    }


def test_raise_ingestion_publish_unavailable_uses_503_retry_after() -> None:
    exc = IngestionPublishError(
        "Delivery confirmation timed out.",
        failed_record_keys=["T1"],
    )

    with pytest.raises(HTTPException) as exc_info:
        raise_ingestion_publish_unavailable(exc, job_id="job_002")

    response = exc_info.value
    assert response.status_code == 503
    assert response.headers == {"Retry-After": "30"}
    assert response.detail["code"] == "INGESTION_PUBLISH_FAILED"
    assert response.detail["dependency"] == "kafka"
    assert response.detail["publish_state"] == "unpublished"
    assert response.detail["published_record_count"] == 0
    assert response.detail["failed_record_keys"] == ["T1"]
    assert response.detail["job_id"] == "job_002"
