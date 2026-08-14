from src.services.ingestion_service.app.application.ingestion_failure_evidence import (
    SAFE_GENERIC_FAILURE_MESSAGE,
    project_ingestion_failure_evidence,
)


def test_failure_evidence_removes_untrusted_text_and_unknown_nested_data() -> None:
    evidence = project_ingestion_failure_evidence(
        failure_code="INGESTION_PUBLISH_FAILED",
        failure_detail={
            "message": "password=secret at kafka.internal:9093 for client@example.com",
            "dependency": "kafka",
            "retryable": True,
            "published_record_count": 1,
            "request_payload": {"portfolio_id": "PB_PRIVATE"},
            "credentials": {"authorization": "Bearer secret"},
        },
        failure_headers={
            "Retry-After": "30",
            "Authorization": "Bearer secret",
            "X-Internal-Host": "kafka.internal",
        },
    )

    assert evidence.reason == "Ingestion publishing failed before durable queue confirmation."
    assert evidence.detail == {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Ingestion publishing failed before durable queue confirmation.",
        "dependency": "kafka",
        "retryable": True,
        "published_record_count": 1,
    }
    assert evidence.headers == {"Retry-After": "30"}
    assert "secret" not in repr(evidence)
    assert "PB_PRIVATE" not in repr(evidence)


def test_failure_evidence_without_stable_code_retains_no_arbitrary_detail() -> None:
    evidence = project_ingestion_failure_evidence(
        failure_code=None,
        failure_detail={"message": "postgresql://user:secret@db.internal/private"},
        failure_headers={"Set-Cookie": "session=secret"},
    )

    assert evidence.reason == SAFE_GENERIC_FAILURE_MESSAGE
    assert evidence.detail is None
    assert evidence.headers is None


def test_failure_evidence_rejects_non_numeric_retry_after() -> None:
    evidence = project_ingestion_failure_evidence(
        failure_code="REFERENCE_DATA_PERSIST_FAILED",
        failure_detail=None,
        failure_headers={"Retry-After": "https://internal/retry?token=secret"},
    )

    assert evidence.headers is None
