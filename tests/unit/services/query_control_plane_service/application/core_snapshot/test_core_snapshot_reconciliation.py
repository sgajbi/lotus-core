from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from portfolio_common.domain.holdings_reconciliation import FinancialReconciliationControl
from portfolio_common.reconciliation_quality import BLOCKED, COMPLETE, STALE

from src.services.query_control_plane_service.app.application.core_snapshot.reconciliation import (
    core_snapshot_reconciliation_evidence,
    core_snapshot_reconciliation_scopes,
    core_snapshot_source_content_hash,
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


def test_core_snapshot_source_hash_is_order_independent_and_value_sensitive() -> None:
    first = _row()
    second = _row(updated_at=datetime(2026, 4, 10, 3, tzinfo=UTC))
    corrected = _row(updated_at=datetime(2026, 4, 10, 4, tzinfo=UTC))

    assert core_snapshot_source_content_hash([first, second]) == (
        core_snapshot_source_content_hash([second, first])
    )
    assert core_snapshot_source_content_hash([first, second]) != (
        core_snapshot_source_content_hash([first, corrected])
    )


def test_core_snapshot_reconciliation_evidence_binds_scopes_and_controls() -> None:
    source_timestamp = datetime(2026, 4, 10, 2, tzinfo=UTC)
    control_timestamp = source_timestamp + timedelta(minutes=5)
    scopes = core_snapshot_reconciliation_scopes([_row(updated_at=source_timestamp)])

    evidence = core_snapshot_reconciliation_evidence(
        scopes=scopes,
        controls=[
            FinancialReconciliationControl(
                business_date=date(2026, 4, 10),
                epoch=4,
                status=" completed ",
                updated_at=control_timestamp,
            )
        ],
    )

    assert evidence.status == COMPLETE
    assert len(evidence.scope_content_hash) == 64
    assert len(evidence.control_content_hash) == 64
    assert evidence.latest_evidence_timestamp == control_timestamp


def test_core_snapshot_reconciliation_evidence_detects_stale_control() -> None:
    source_timestamp = datetime(2026, 4, 10, 2, tzinfo=UTC)
    scopes = core_snapshot_reconciliation_scopes([_row(updated_at=source_timestamp)])

    evidence = core_snapshot_reconciliation_evidence(
        scopes=scopes,
        controls=[
            FinancialReconciliationControl(
                business_date=date(2026, 4, 10),
                epoch=4,
                status="COMPLETED",
                updated_at=source_timestamp - timedelta(minutes=1),
            )
        ],
    )

    assert evidence.status == STALE


def test_core_snapshot_duplicate_control_evidence_is_order_independent_and_fail_closed() -> None:
    source_timestamp = datetime(2026, 4, 10, 2, tzinfo=UTC)
    scopes = core_snapshot_reconciliation_scopes([_row(updated_at=source_timestamp)])
    controls = [
        FinancialReconciliationControl(
            business_date=date(2026, 4, 10),
            epoch=4,
            status="COMPLETED",
            updated_at=source_timestamp + timedelta(minutes=5),
        ),
        FinancialReconciliationControl(
            business_date=date(2026, 4, 10),
            epoch=4,
            status="REQUIRES_REPLAY",
            updated_at=source_timestamp + timedelta(minutes=4),
        ),
    ]

    first = core_snapshot_reconciliation_evidence(scopes=scopes, controls=controls)
    reordered = core_snapshot_reconciliation_evidence(
        scopes=scopes,
        controls=list(reversed(controls)),
    )

    assert first.status == BLOCKED
    assert reordered.status == BLOCKED
    assert first.control_content_hash == reordered.control_content_hash
