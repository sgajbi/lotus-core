from datetime import UTC, datetime

import pytest
from portfolio_common.reconciliation_quality import (
    BLOCKED,
    BREAK_OPEN,
    COMPLETE,
    PARTIAL,
    STALE,
    UNKNOWN,
    UNRECONCILED,
    DataQualityCoverageSignal,
    ReconciliationBreakSignal,
    ReconciliationRunSignal,
    aggregate_reconciliation_statuses,
    classify_data_quality_coverage,
    classify_finding_status,
    classify_reconciliation_status,
    evidence_age_minutes,
    is_evidence_stale,
    is_finding_open,
    normalize_finding_resolution_state,
    reconciliation_bound_data_quality_status,
    sort_reconciliation_breaks,
)


@pytest.mark.parametrize(
    ("signal", "expected"),
    [
        (ReconciliationRunSignal(run_status="COMPLETED"), COMPLETE),
        (ReconciliationRunSignal(run_status="completed", warning_count=1), PARTIAL),
        (ReconciliationRunSignal(run_status="COMPLETED", error_count=1), BLOCKED),
        (ReconciliationRunSignal(run_status="REQUIRES_REPLAY"), BLOCKED),
        (ReconciliationRunSignal(run_status="FAILED"), BLOCKED),
        (ReconciliationRunSignal(run_status="FAILED", is_stale=True), BLOCKED),
        (ReconciliationRunSignal(run_status="COMPLETED", error_count=1, is_stale=True), BLOCKED),
        (ReconciliationRunSignal(run_status="RUNNING"), PARTIAL),
        (ReconciliationRunSignal(run_status="COMPLETED", is_stale=True), STALE),
        (ReconciliationRunSignal(run_status=None), UNKNOWN),
        (ReconciliationRunSignal(run_status=None, has_run=False), UNRECONCILED),
    ],
)
def test_classify_reconciliation_status(signal, expected) -> None:
    assert classify_reconciliation_status(signal) == expected


@pytest.mark.parametrize(
    ("severity", "resolution_state", "expected"),
    [
        ("ERROR", "OPEN", BLOCKED),
        ("CRITICAL", "OPEN", BLOCKED),
        ("WARNING", "OPEN", BREAK_OPEN),
        ("INFO", "OPEN", BREAK_OPEN),
        ("ERROR", "RESOLVED", COMPLETE),
        ("ERROR", "WAIVED", COMPLETE),
        ("NOTICE", "OPEN", UNKNOWN),
    ],
)
def test_classify_finding_status(severity, resolution_state, expected) -> None:
    assert classify_finding_status(severity=severity, resolution_state=resolution_state) == expected


@pytest.mark.parametrize(
    ("signal", "expected"),
    [
        (DataQualityCoverageSignal(required_count=10, observed_count=10), COMPLETE),
        (DataQualityCoverageSignal(required_count=10, observed_count=8), PARTIAL),
        (
            DataQualityCoverageSignal(required_count=10, observed_count=10, warning_issue_count=1),
            PARTIAL,
        ),
        (DataQualityCoverageSignal(required_count=10, observed_count=10, stale_count=1), STALE),
        (
            DataQualityCoverageSignal(required_count=10, observed_count=10, blocking_issue_count=1),
            BLOCKED,
        ),
        (DataQualityCoverageSignal(required_count=10, observed_count=0), UNRECONCILED),
        (DataQualityCoverageSignal(required_count=0, observed_count=0), UNKNOWN),
    ],
)
def test_classify_data_quality_coverage(signal, expected) -> None:
    assert classify_data_quality_coverage(signal) == expected


@pytest.mark.parametrize(
    ("source_status", "reconciliation_status", "expected"),
    [
        (COMPLETE, COMPLETE, COMPLETE),
        (PARTIAL, COMPLETE, PARTIAL),
        (COMPLETE, PARTIAL, PARTIAL),
        (COMPLETE, BREAK_OPEN, PARTIAL),
        (COMPLETE, UNRECONCILED, UNKNOWN),
        (UNKNOWN, COMPLETE, UNKNOWN),
        (COMPLETE, STALE, STALE),
        (STALE, BLOCKED, BLOCKED),
        (COMPLETE, BLOCKED, BLOCKED),
        ("unexpected", COMPLETE, UNKNOWN),
    ],
)
def test_reconciliation_bound_data_quality_status_fails_closed(
    source_status: str,
    reconciliation_status: str,
    expected: str,
) -> None:
    assert (
        reconciliation_bound_data_quality_status(
            source_data_quality_status=source_status,
            reconciliation_status=reconciliation_status,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([COMPLETE, BLOCKED], BLOCKED),
        ([UNKNOWN, STALE], STALE),
        ([COMPLETE, BREAK_OPEN, STALE], STALE),
        ([UNKNOWN, PARTIAL], UNKNOWN),
        ([COMPLETE, UNRECONCILED], UNRECONCILED),
        ([COMPLETE, " stale "], STALE),
        ([COMPLETE, None], UNKNOWN),
        ([COMPLETE, "unexpected"], UNKNOWN),
        ([COMPLETE, COMPLETE], COMPLETE),
        ([], UNKNOWN),
    ],
)
def test_aggregate_reconciliation_statuses_uses_governed_precedence(
    statuses: list[str | None],
    expected: str,
) -> None:
    assert aggregate_reconciliation_statuses(statuses) == expected


def test_aggregate_reconciliation_statuses_supports_domain_empty_status() -> None:
    assert aggregate_reconciliation_statuses([], empty_status=UNRECONCILED) == UNRECONCILED


def test_sort_reconciliation_breaks_prioritizes_blocking_severity_age_and_id() -> None:
    breaks = [
        ReconciliationBreakSignal("finding-warning", "WARNING", False, age_days=30),
        ReconciliationBreakSignal("finding-error-young", "ERROR", True, age_days=1),
        ReconciliationBreakSignal("finding-critical", "CRITICAL", True, age_days=2),
        ReconciliationBreakSignal("finding-error-old", "ERROR", True, age_days=5),
    ]

    ordered = sort_reconciliation_breaks(breaks)

    assert [item.finding_id for item in ordered] == [
        "finding-critical",
        "finding-error-old",
        "finding-error-young",
        "finding-warning",
    ]


def test_classifiers_reject_invalid_counts_and_blank_text() -> None:
    with pytest.raises(ValueError, match="error_count must be non-negative"):
        classify_reconciliation_status(
            ReconciliationRunSignal(run_status="COMPLETED", error_count=-1)
        )

    with pytest.raises(ValueError, match="required_count must be non-negative"):
        classify_data_quality_coverage(
            DataQualityCoverageSignal(required_count=-1, observed_count=0)
        )

    with pytest.raises(ValueError, match="severity is required"):
        classify_finding_status(severity=" ", resolution_state="OPEN")


def test_finding_resolution_and_evidence_age_helpers_fail_closed() -> None:
    assert normalize_finding_resolution_state(" in_progress ") == "IN_PROGRESS"
    assert is_finding_open("IN_PROGRESS") is True
    assert is_finding_open("RESOLVED") is False
    with pytest.raises(ValueError, match="resolution_state must be one of"):
        normalize_finding_resolution_state("CLOSED")

    generated_at = datetime(2026, 7, 31, 10, tzinfo=UTC)
    age = evidence_age_minutes(
        generated_at=generated_at,
        evidence_timestamp=datetime(2026, 7, 31, 9, 44, tzinfo=UTC),
    )
    assert age == 16
    assert is_evidence_stale(evidence_age_minutes=age, threshold_minutes=15) is True
    assert is_evidence_stale(evidence_age_minutes=None, threshold_minutes=15) is False
