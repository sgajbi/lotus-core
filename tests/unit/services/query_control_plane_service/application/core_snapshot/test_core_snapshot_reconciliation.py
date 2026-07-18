from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from src.services.query_control_plane_service.app.application.core_snapshot.reconciliation import (
    core_snapshot_reconciliation_scopes,
)
from src.services.query_control_plane_service.app.domain.core_snapshot import (
    CoreSnapshotInstrument,
    CoreSnapshotPositionSource,
)


def _row(
    *,
    business_date: date | None = date(2026, 4, 10),
    epoch: int = 4,
    updated_at: datetime = datetime(2026, 4, 10, 2, tzinfo=UTC),
) -> CoreSnapshotPositionSource:
    return CoreSnapshotPositionSource(
        security_id="SEC_1",
        quantity=Decimal("1"),
        market_value=Decimal("100"),
        market_value_local=Decimal("100"),
        cost_basis=None,
        cost_basis_local=None,
        epoch=epoch,
        source_created_at=updated_at - timedelta(hours=1),
        source_updated_at=updated_at,
        state_created_at=None,
        state_updated_at=updated_at - timedelta(minutes=1),
        instrument=CoreSnapshotInstrument(
            security_id="SEC_1",
            name="Instrument",
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
        business_date=business_date,
    )


def test_core_snapshot_scopes_coalesce_exact_date_epoch_rows() -> None:
    scopes = core_snapshot_reconciliation_scopes([_row(), _row()])

    assert len(scopes.items) == 1
    assert scopes.items[0].business_date == date(2026, 4, 10)
    assert scopes.items[0].epoch == 4
    assert scopes.items[0].source_row_count == 2
    assert scopes.items[0].latest_evidence_timestamp == datetime(2026, 4, 10, 2, tzinfo=UTC)
    assert scopes.unscoped_source_row_count == 0
    assert len(scopes.content_hash()) == 64


def test_core_snapshot_scopes_fail_closed_for_unscoped_rows() -> None:
    scopes = core_snapshot_reconciliation_scopes([_row(business_date=None)])

    assert scopes.items == ()
    assert scopes.unscoped_source_row_count == 1
