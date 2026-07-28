from src.services.ingestion_service.app.application.ingestion_publish_outcome import (
    build_ingestion_publish_failure_detail,
)


def test_publish_failure_detail_preserves_partial_publication_and_lineage() -> None:
    failed_keys = ["TX-002", "TX-003"]

    detail = build_ingestion_publish_failure_detail(
        message="Kafka publish failed after one record.",
        failed_record_keys=failed_keys,
        published_record_count=1,
        job_id="ing_job_001",
        correlation_id="corr-001",
        request_id="req-001",
        trace_id="trace-001",
    )

    assert detail == {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Kafka publish failed after one record.",
        "dependency": "kafka",
        "retryable": True,
        "retry_after_seconds": 30,
        "publish_state": "partial",
        "published_record_count": 1,
        "failed_record_keys": ["TX-002", "TX-003"],
        "job_id": "ing_job_001",
        "correlation_id": "corr-001",
        "request_id": "req-001",
        "trace_id": "trace-001",
    }
    assert detail["failed_record_keys"] is not failed_keys
