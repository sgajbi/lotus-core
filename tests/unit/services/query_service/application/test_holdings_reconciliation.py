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
) -> FinancialReconciliationControl:
    return FinancialReconciliationControl(
        business_date=date(2026, 3, 10),
        epoch=2,
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


def test_empty_holdings_without_control_scope_are_unreconciled() -> None:
    assert (
        holdings_reconciliation_status(
            scopes=HoldingsReconciliationScopes(items=()),
            controls=[],
        )
        == UNRECONCILED
    )
