from datetime import date
from decimal import Decimal

from scripts.offline_integrity_auditor import (
    LedgerRow,
    PositionKey,
    SnapshotRow,
    _aggregate_ledger_positions,
    _compare_positions,
    _latest_snapshot_positions,
    _signed_quantity,
)


def test_signed_quantity_maps_buy_sell_and_ignores_unsupported() -> None:
    assert _signed_quantity("BUY", Decimal("10")) == Decimal("10")
    assert _signed_quantity("SELL", Decimal("10")) == Decimal("-10")
    assert _signed_quantity("DIVIDEND", Decimal("10")) == Decimal("0")


def test_aggregate_ledger_positions_accumulates_signed_holdings() -> None:
    rows = [
        LedgerRow("P1", "S1", "BUY", Decimal("100"), date(2026, 1, 1)),
        LedgerRow("P1", "S1", "SELL", Decimal("35"), date(2026, 1, 2)),
        LedgerRow("P1", "S2", "BUY", Decimal("20"), date(2026, 1, 3)),
    ]
    positions = _aggregate_ledger_positions(rows)
    assert positions[PositionKey("P1", "S1")] == Decimal("65")
    assert positions[PositionKey("P1", "S2")] == Decimal("20")


def test_latest_snapshot_positions_picks_latest_date_then_epoch() -> None:
    rows = [
        SnapshotRow("P1", "S1", Decimal("40"), date(2026, 1, 2), 0),
        SnapshotRow("P1", "S1", Decimal("45"), date(2026, 1, 2), 1),
        SnapshotRow("P1", "S1", Decimal("42"), date(2026, 1, 1), 9),
    ]
    latest = _latest_snapshot_positions(rows)
    assert latest[PositionKey("P1", "S1")] == Decimal("45")


def test_compare_positions_flags_missing_and_mismatch() -> None:
    ledger = {
        PositionKey("P1", "S1"): Decimal("100"),
        PositionKey("P1", "S2"): Decimal("50"),
    }
    snapshot = {
        PositionKey("P1", "S1"): Decimal("99"),
        PositionKey("P1", "S3"): Decimal("10"),
    }
    mismatches = _compare_positions(ledger, snapshot, tolerance=Decimal("0.0001"))
    by_key = {(m.portfolio_id, m.security_id): m for m in mismatches}
    assert by_key[("P1", "S1")].classification == "quantity_mismatch"
    assert by_key[("P1", "S2")].classification == "missing_snapshot"
    assert by_key[("P1", "S3")].classification == "missing_ledger"
