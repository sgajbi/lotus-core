"""Prove deterministic evaluation of the derived-state poison recovery gate."""

from scripts.operations.recovery.derived_state_gate import DerivedStateCounts
from scripts.operations.recovery.derived_state_poison_gate import (
    matching_support_events,
    validate_poison_recovery,
)


def test_matching_support_events_requires_exact_source_identity() -> None:
    payload = {
        "events": [
            {
                "event_id": "cdlq-match",
                "original_topic": "valuation.snapshot.persisted",
                "consumer_group": "timeseries_generator_group_positions",
                "dlq_topic": "dlq.persistence_service",
                "original_key": "POISON-01",
                "correlation_id": "DPS:01",
                "error_reason_code": "VALIDATION_ERROR",
            },
            {
                "event_id": "cdlq-other",
                "original_topic": "valuation.snapshot.persisted",
                "consumer_group": "timeseries_generator_group_positions",
                "dlq_topic": "dlq.persistence_service",
                "original_key": "POISON-02",
                "correlation_id": "DPS:02",
                "error_reason_code": "VALIDATION_ERROR",
            },
        ],
        "total": 2,
    }

    matches = matching_support_events(
        payload,
        original_key="POISON-01",
        correlation_id="DPS:01",
        source_topic="valuation.snapshot.persisted",
        consumer_group="timeseries_generator_group_positions",
    )

    assert matches == (payload["events"][0],)


def test_validate_poison_recovery_accepts_one_dlq_and_complete_valid_progress() -> None:
    failures = validate_poison_recovery(
        expected_position_count=1,
        baseline_consumer_lag=0,
        final_consumer_lag=0,
        baseline_dlq_high_watermark=0,
        final_dlq_high_watermark=1,
        matching_support_event_count=1,
        support_reason_codes=("VALIDATION_ERROR",),
        recovery_seconds=2.5,
        max_recovery_seconds=60,
        counts=DerivedStateCounts(1, 1, 1, 0, 0),
        reconciliation_finding_count=0,
    )

    assert failures == ()


def test_validate_poison_recovery_reports_every_broken_invariant() -> None:
    failures = validate_poison_recovery(
        expected_position_count=1,
        baseline_consumer_lag=0,
        final_consumer_lag=2,
        baseline_dlq_high_watermark=4,
        final_dlq_high_watermark=6,
        matching_support_event_count=2,
        support_reason_codes=("UNCLASSIFIED_PROCESSING_ERROR",),
        recovery_seconds=None,
        max_recovery_seconds=60,
        counts=DerivedStateCounts(0, 0, 0, 1, 1),
        reconciliation_finding_count=1,
    )

    assert failures == (
        "consumer lag after recovery 2 exceeded baseline 0",
        "DLQ topic grew by 2 records instead of exactly 1",
        "support plane exposed 2 matching poison events instead of exactly 1",
        "support reason codes ('UNCLASSIFIED_PROCESSING_ERROR',) did not equal "
        "('VALIDATION_ERROR',)",
        "valid message did not recover before timeout",
        "snapshot_count 0 != expected 1",
        "position_timeseries_count 0 != expected 1",
        "portfolio_timeseries_count 0 != expected 1",
        "open_valuation_job_count 1 != expected 0",
        "open_aggregation_job_count 1 != expected 0",
        "reconciliation returned 1 findings",
    )
