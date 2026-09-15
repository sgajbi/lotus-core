from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.holdings_reconciliation import (
    HoldingsReconciliationScope,
    HoldingsReconciliationScopes,
)

from src.services.query_control_plane_service.app.application.core_snapshot.baseline_metadata import (  # noqa: E501
    baseline_freshness_metadata,
    baseline_snapshot_epoch,
    latest_snapshot_timestamp,
)
from src.services.query_control_plane_service.app.application.core_snapshot.reconciliation import (
    core_snapshot_reconciliation_scopes,
)
from src.services.query_control_plane_service.app.domain.core_snapshot import (
    CoreSnapshotInstrument,
    CoreSnapshotPositionSource,
)


def _row_state(
    *,
    row_created_at: datetime | None = None,
    row_updated_at: datetime | None = None,
    state_created_at: datetime | None = None,
    state_updated_at: datetime | None = None,
    epoch: int | None = None,
) -> CoreSnapshotPositionSource:
    return CoreSnapshotPositionSource(
        security_id="SEC_TEST",
        quantity=Decimal("1"),
        market_price=Decimal("1"),
        market_value=Decimal("1"),
        market_value_local=Decimal("1"),
        cost_basis=None,
        cost_basis_local=None,
        epoch=epoch or 0,
        state_epoch=epoch or 0,
        state_status="CURRENT",
        source_created_at=row_created_at,
        source_updated_at=row_updated_at,
        state_created_at=state_created_at,
        state_updated_at=state_updated_at,
        instrument=CoreSnapshotInstrument(
            security_id="SEC_TEST",
            name="Test",
            currency="USD",
            asset_class="EQUITY",
            sector=None,
            country_of_risk=None,
            isin=None,
            issuer_id=None,
            issuer_name=None,
            ultimate_parent_issuer_id=None,
            ultimate_parent_issuer_name=None,
            liquidity_tier=None,
        ),
        valuation_status="VALUED_CURRENT",
        portfolio_business_date=date(2026, 2, 27),
    )


def test_baseline_freshness_metadata_marks_history_fallback() -> None:
    freshness = baseline_freshness_metadata(
        rows=[],
        reconciliation_scopes=core_snapshot_reconciliation_scopes([]),
        use_snapshot=False,
        has_baseline=False,
    )

    assert freshness.freshness_status == "HISTORICAL_FALLBACK"
    assert freshness.baseline_source == "position_history"
    assert freshness.snapshot_timestamp is None
    assert freshness.snapshot_epoch is None
    assert freshness.fallback_reason == "NO_CURRENT_POSITION_STATE_ROWS"


def test_baseline_freshness_metadata_uses_snapshot_timestamp_and_epoch() -> None:
    rows = [
        _row_state(
            row_created_at=datetime(2026, 2, 27, 9, 30, tzinfo=UTC),
            row_updated_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            state_updated_at=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
            epoch=7,
        )
    ]
    freshness = baseline_freshness_metadata(
        rows=rows,
        reconciliation_scopes=core_snapshot_reconciliation_scopes(rows),
        use_snapshot=True,
        has_baseline=True,
    )

    assert freshness.freshness_status == "CURRENT_SNAPSHOT"
    assert freshness.baseline_source == "position_state"
    assert freshness.snapshot_timestamp == datetime(2026, 2, 27, 10, 5, tzinfo=UTC)
    assert freshness.snapshot_epoch == 7
    assert freshness.fallback_reason is None


def test_latest_snapshot_timestamp_returns_latest_row_or_state_timestamp() -> None:
    latest = latest_snapshot_timestamp(
        [
            _row_state(
                row_created_at=datetime(2026, 2, 27, 9, 30, tzinfo=UTC),
                row_updated_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
                state_updated_at=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
            )
        ]
    )

    assert latest == datetime(2026, 2, 27, 10, 5, tzinfo=UTC)


def test_baseline_snapshot_epoch_handles_empty_and_mixed_epochs() -> None:
    assert (
        baseline_snapshot_epoch(scopes=core_snapshot_reconciliation_scopes([]), has_baseline=False)
        is None
    )
    assert (
        baseline_snapshot_epoch(
            scopes=core_snapshot_reconciliation_scopes([_row_state(epoch=7), _row_state(epoch=99)]),
            has_baseline=True,
        )
        == 99
    )


@pytest.mark.parametrize(
    "invalid_row",
    [
        replace(_row_state(epoch=1), state_epoch=2),
        replace(_row_state(epoch=1), portfolio_business_date=None),
        replace(_row_state(epoch=1), epoch=-1, state_epoch=-1),
        replace(_row_state(epoch=1), epoch=True, state_epoch=True),
    ],
)
def test_baseline_snapshot_epoch_refuses_any_unscoped_source(invalid_row) -> None:
    rows = [_row_state(epoch=0), invalid_row]
    scopes = core_snapshot_reconciliation_scopes(rows)
    assert scopes.unscoped_source_row_count == 1
    freshness = baseline_freshness_metadata(
        rows=rows, reconciliation_scopes=scopes, use_snapshot=True, has_baseline=True
    )
    assert freshness.snapshot_epoch is None


def test_baseline_snapshot_epoch_preserves_empty_filtered_baseline_truth() -> None:
    assert (
        baseline_snapshot_epoch(
            scopes=core_snapshot_reconciliation_scopes([_row_state(epoch=7)]),
            has_baseline=False,
        )
        is None
    )


def test_baseline_snapshot_epoch_refuses_missing_or_conflicting_collective_targets() -> None:
    assert (
        baseline_snapshot_epoch(scopes=HoldingsReconciliationScopes(items=()), has_baseline=True)
        is None
    )
    scopes = HoldingsReconciliationScopes(
        items=tuple(
            HoldingsReconciliationScope(
                business_date=date(2026, 2, day),
                epoch=epoch,
                latest_evidence_timestamp=None,
                source_row_count=1,
            )
            for day, epoch in [(26, 7), (27, 8)]
        )
    )
    assert baseline_snapshot_epoch(scopes=scopes, has_baseline=True) is None
