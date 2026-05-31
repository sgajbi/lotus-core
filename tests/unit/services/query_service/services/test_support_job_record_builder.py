from datetime import date, datetime, timedelta, timezone

from src.services.query_service.app.services.support_job_record_builder import (
    build_support_job_record,
    get_support_job_operational_state,
    is_support_job_stale,
    normalize_support_job_status,
)


def test_support_job_record_builder_normalizes_status_and_security_id() -> None:
    now = datetime(2026, 4, 18, 8, 0, tzinfo=timezone.utc)

    record = build_support_job_record(
        job_id=101,
        job_type="VALUATION",
        business_date=date(2026, 4, 17),
        status=" failed ",
        security_id=" sec-1 ",
        epoch=3,
        attempt_count=2,
        correlation_id="corr-101",
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=1),
        failure_reason="pricing gap",
        reference_now=now,
    )

    assert record.security_id == "sec-1"
    assert record.is_terminal_failure is True
    assert record.is_retrying is False
    assert record.operational_state == "FAILED"


def test_support_job_record_builder_classifies_processing_staleness() -> None:
    now = datetime(2026, 4, 18, 8, 0, tzinfo=timezone.utc)
    stale_updated_at = now - timedelta(minutes=20)
    fresh_updated_at = now - timedelta(minutes=5)

    assert normalize_support_job_status(" processing ") == "PROCESSING"
    assert is_support_job_stale("PROCESSING", stale_updated_at, now=now) is True
    assert is_support_job_stale("PROCESSING", fresh_updated_at, now=now) is False
    assert (
        get_support_job_operational_state("PROCESSING", stale_updated_at, now=now)
        == "STALE_PROCESSING"
    )
    assert (
        get_support_job_operational_state("PROCESSING", fresh_updated_at, now=now) == "PROCESSING"
    )
