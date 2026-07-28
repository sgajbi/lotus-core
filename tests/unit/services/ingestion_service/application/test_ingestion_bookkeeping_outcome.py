from src.services.ingestion_service.app.application.ingestion_bookkeeping_outcome import (
    build_ingestion_bookkeeping_failure_detail,
)


def test_bookkeeping_failure_detail_is_source_safe_and_replay_complete() -> None:
    detail = build_ingestion_bookkeeping_failure_detail(
        job_id="ing_job_001",
        failure_phase="persist_bookkeeping",
        publish_state="not_published",
        work_state="persisted",
        published_record_count=0,
        correlation_id="corr-001",
        request_id="req-001",
        trace_id="trace-001",
    )

    assert detail == {
        "code": "INGESTION_JOB_BOOKKEEPING_FAILED",
        "message": "Ingestion work completed, but job bookkeeping did not complete afterward.",
        "job_id": "ing_job_001",
        "publish_state": "not_published",
        "work_state": "persisted",
        "published_record_count": 0,
        "retry_safe": False,
        "recovery_action": "repair_ingestion_job_bookkeeping",
        "recovery_path": "ingestion_job_bookkeeping_repair",
        "supportability_reason_code": "POST_PERSIST_BOOKKEEPING_FAILED",
        "remediation": (
            "Inspect the job failure history, confirm published or persisted work, then run "
            "the governed bookkeeping repair action before client retry."
        ),
        "correlation_id": "corr-001",
        "request_id": "req-001",
        "trace_id": "trace-001",
    }
