from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.services.query_control_plane_service.app.application.core_snapshot.baseline_metadata import (  # noqa: E501
    baseline_freshness_metadata,
    baseline_snapshot_epoch,
    latest_snapshot_timestamp,
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
        market_value=Decimal("1"),
        market_value_local=Decimal("1"),
        cost_basis=None,
        cost_basis_local=None,
        epoch=epoch or 0,
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
    )


def test_baseline_freshness_metadata_marks_history_fallback() -> None:
    freshness = baseline_freshness_metadata(
        rows=[],
        use_snapshot=False,
        has_baseline=False,
    )

    assert freshness.freshness_status == "HISTORICAL_FALLBACK"
    assert freshness.baseline_source == "position_history"
    assert freshness.snapshot_timestamp is None
    assert freshness.snapshot_epoch is None
    assert freshness.fallback_reason == "NO_CURRENT_POSITION_STATE_ROWS"


def test_baseline_freshness_metadata_uses_snapshot_timestamp_and_epoch() -> None:
    freshness = baseline_freshness_metadata(
        rows=[
            _row_state(
                row_created_at=datetime(2026, 2, 27, 9, 30, tzinfo=UTC),
                row_updated_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
                state_updated_at=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
                epoch=7,
            )
        ],
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
    assert baseline_snapshot_epoch(rows=[], has_baseline=False) is None
    assert (
        baseline_snapshot_epoch(
            rows=[_row_state(epoch=7), _row_state(epoch=99)],
            has_baseline=True,
        )
        is None
    )
