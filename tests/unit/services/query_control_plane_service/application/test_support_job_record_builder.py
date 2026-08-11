from datetime import date, datetime, timedelta, timezone

from src.services.query_control_plane_service.app.application.operations.support_jobs import (
    build_support_job_record,
    get_support_job_operational_state,
    is_support_job_stale,
    normalize_support_job_status,
    parse_support_job_business_date,
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


def test_support_job_record_builder_prefers_authoritative_lease_deadline() -> None:
    now = datetime(2026, 4, 18, 8, 0, tzinfo=timezone.utc)
    recently_updated = now - timedelta(minutes=1)

    expired = build_support_job_record(
        job_id=202,
        job_type="VALUATION",
        business_date=date(2026, 4, 17),
        status="PROCESSING",
        security_id="SEC-2",
        epoch=1,
        attempt_count=1,
        correlation_id="corr-202",
        created_at=now - timedelta(minutes=2),
        updated_at=recently_updated,
        failure_reason=None,
        reference_now=now,
        stale_threshold_minutes=60,
        stale_deadline=now,
    )

    assert expired.is_stale_processing is True
    assert expired.operational_state == "STALE_PROCESSING"
    assert (
        is_support_job_stale(
            "PROCESSING",
            recently_updated,
            now=now,
            stale_threshold_minutes=60,
            stale_deadline=now + timedelta(seconds=1),
        )
        is False
    )


def test_support_job_business_date_parser_preserves_malformed_replay_visibility() -> None:
    assert parse_support_job_business_date("2026-04-10") == date(2026, 4, 10)
    assert parse_support_job_business_date("not-a-date") is None
    assert parse_support_job_business_date(None) is None
