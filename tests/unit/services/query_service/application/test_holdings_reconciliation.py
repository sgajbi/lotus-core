from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from portfolio_common.reconciliation_quality import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    STALE,
    UNKNOWN,
    UNRECONCILED,
)

from src.services.query_service.app.application.holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationScopes,
    holdings_reconciliation_scopes,
    holdings_reconciliation_status,
)

EVIDENCE_AT = datetime(2026, 3, 10, 12, tzinfo=UTC)


def _source_row(
    *,
    business_date: date = date(2026, 3, 10),
    epoch: int = 2,
    state_epoch: int | None = None,
    updated_at: datetime = EVIDENCE_AT,
):
    return (
        SimpleNamespace(date=business_date, epoch=epoch, updated_at=updated_at),
        SimpleNamespace(updated_at=updated_at - timedelta(minutes=2)),
        SimpleNamespace(epoch=epoch if state_epoch is None else state_epoch, updated_at=updated_at),
    )


def _control(
    *,
    status: str = "COMPLETED",
    updated_at: datetime = EVIDENCE_AT,
    epoch: int = 2,
) -> FinancialReconciliationControl:
    return FinancialReconciliationControl(
        business_date=date(2026, 3, 10),
        epoch=epoch,
        status=status,
        updated_at=updated_at,
    )


def test_scopes_coalesce_rows_and_hash_deterministically() -> None:
    first = holdings_reconciliation_scopes([_source_row(), _source_row()])
    reordered = holdings_reconciliation_scopes([_source_row(), _source_row()])

    assert len(first.items) == 1
    assert first.items[0].source_row_count == 2
    assert first.items[0].latest_evidence_timestamp == EVIDENCE_AT
    assert first.unscoped_source_row_count == 0
    assert first.content_hash() == reordered.content_hash()
    assert len(first.content_hash()) == 64


def test_scopes_use_collective_maximum_epoch_for_mixed_security_rows() -> None:
    latest_evidence = EVIDENCE_AT + timedelta(minutes=3)
    rows = [
        _source_row(epoch=0, updated_at=latest_evidence),
        _source_row(epoch=1, updated_at=EVIDENCE_AT),
        _source_row(epoch=3, updated_at=EVIDENCE_AT + timedelta(minutes=1)),
    ]

    scopes = holdings_reconciliation_scopes(rows)
    reordered = holdings_reconciliation_scopes(list(reversed(rows)))

    assert len(scopes.items) == 1
    assert scopes.items[0].epoch == 3
    assert scopes.items[0].source_row_count == 3
    assert scopes.items[0].latest_evidence_timestamp == latest_evidence
    assert scopes.content_hash() == reordered.content_hash()
    assert (
        holdings_reconciliation_status(
            scopes=scopes,
            controls=[_control(epoch=3, updated_at=latest_evidence)],
        )
        == COMPLETE
    )


def test_collective_scope_is_stale_when_any_lower_epoch_row_has_newer_evidence() -> None:
    latest_evidence = EVIDENCE_AT + timedelta(minutes=3)
    scopes = holdings_reconciliation_scopes(
        [
            _source_row(epoch=0, updated_at=latest_evidence),
            _source_row(epoch=3, updated_at=EVIDENCE_AT),
        ]
    )

    assert (
        holdings_reconciliation_status(
            scopes=scopes,
            controls=[_control(epoch=3, updated_at=latest_evidence - timedelta(seconds=1))],
        )
        == STALE
    )


def test_completed_control_after_latest_evidence_is_complete() -> None:
    scopes = holdings_reconciliation_scopes([_source_row()])

    status = holdings_reconciliation_status(scopes=scopes, controls=[_control()])

    assert status == COMPLETE


def test_completed_control_before_latest_evidence_is_stale() -> None:
    scopes = holdings_reconciliation_scopes([_source_row()])

    status = holdings_reconciliation_status(
        scopes=scopes,
        controls=[_control(updated_at=EVIDENCE_AT - timedelta(seconds=1))],
    )

    assert status == STALE


@pytest.mark.parametrize("reverse_controls", [False, True])
def test_duplicate_controls_aggregate_worst_status_independent_of_row_order(
    reverse_controls: bool,
) -> None:
    scopes = holdings_reconciliation_scopes([_source_row()])
    controls = [_control(status="COMPLETED"), _control(status="REQUIRES_REPLAY")]
    if reverse_controls:
        controls.reverse()

    status = holdings_reconciliation_status(scopes=scopes, controls=controls)

    assert status == BLOCKED


@pytest.mark.parametrize(
    ("control_status", "expected"),
    [
        ("PENDING", PARTIAL),
        ("RUNNING", PARTIAL),
        ("REQUIRES_REPLAY", BLOCKED),
        ("FAILED", BLOCKED),
        ("legacy", UNKNOWN),
    ],
)
def test_control_statuses_fail_closed(control_status: str, expected: str) -> None:
    scopes = holdings_reconciliation_scopes([_source_row()])

    status = holdings_reconciliation_status(
        scopes=scopes,
        controls=[_control(status=control_status)],
    )

    assert status == expected


def test_missing_control_is_unreconciled() -> None:
    scopes = holdings_reconciliation_scopes([_source_row()])

    assert holdings_reconciliation_status(scopes=scopes, controls=[]) == UNRECONCILED


def test_epoch_mismatch_is_unknown_even_with_an_unrelated_control() -> None:
    scopes = holdings_reconciliation_scopes([_source_row(state_epoch=3)])

    assert scopes.unscoped_source_row_count == 1
    assert holdings_reconciliation_status(scopes=scopes, controls=[_control()]) == UNKNOWN


@pytest.mark.parametrize("invalid_epoch", [-1, True])
def test_invalid_epoch_is_unscoped_and_unknown(invalid_epoch: int) -> None:
    scopes = holdings_reconciliation_scopes(
        [_source_row(epoch=invalid_epoch, state_epoch=invalid_epoch)]
    )

    assert scopes.items == ()
    assert scopes.unscoped_source_row_count == 1
    assert holdings_reconciliation_status(scopes=scopes, controls=[_control()]) == UNKNOWN


def test_empty_holdings_without_control_scope_are_unreconciled() -> None:
    assert (
        holdings_reconciliation_status(
            scopes=HoldingsReconciliationScopes(items=()),
            controls=[],
        )
        == UNRECONCILED
    )
