from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.application.cash_balance_evidence import (
    cash_balance_evidence,
)
from src.services.query_service.app.application.holdings_reconciliation import (
    FinancialReconciliationControl,
)

DAY = date(2026, 12, 31)
AT = datetime(2026, 12, 31, 12, tzinfo=UTC)


def source(*, security="CASH_USD", quantity="0", epoch=1, asset_class="CASH"):
    return SimpleNamespace(
        snapshot=SimpleNamespace(
            id=1,
            security_id=security,
            date=DAY,
            epoch=epoch,
            quantity=Decimal(quantity),
            market_value=Decimal(quantity),
            market_value_local=Decimal(quantity),
            valuation_status="VALUED_CURRENT",
            valuation_source_currency="USD",
            valuation_reporting_currency="USD",
            valuation_fx_rate=None,
            valuation_fx_rate_date=None,
            created_at=AT,
            updated_at=AT,
        ),
        instrument=SimpleNamespace(asset_class=asset_class, created_at=AT, updated_at=AT),
        position_state=SimpleNamespace(epoch=epoch, status="CURRENT", updated_at=AT),
    )


def qualify(rows, *, controls=None, records=None, expected=0):
    return cash_balance_evidence(
        rows=rows,
        account_records=records
        or [
            SimpleNamespace(
                security_id="CASH_USD",
                account_currency="USD",
                cash_account_id_source="cash_account_master",
            )
        ],
        resolved_as_of_date=DAY,
        portfolio_currency="USD",
        expected_open_position_count=expected,
        controls=controls
        if controls is not None
        else [FinancialReconciliationControl(DAY, 1, "COMPLETED", AT + timedelta(seconds=1))],
    )


def test_explicit_zero_requires_exact_collective_reconciliation():
    rows = [source(), source(security="EQUITY", quantity="10", epoch=2, asset_class="EQUITY")]
    assert not qualify(rows, expected=1).source_evidence_current
    proof = qualify(
        rows,
        expected=1,
        controls=[FinancialReconciliationControl(DAY, 2, "COMPLETED", AT + timedelta(seconds=1))],
    )
    assert proof.data_quality_status == "COMPLETE"
    assert proof.source_evidence_current


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_control",
        "wrong_day",
        "wrong_epoch",
        "pending",
        "failed",
        "replay",
        "stale_control",
        "missing_control_time",
        "old_snapshot",
        "missing_value",
        "missing_local",
        "missing_currency",
        "wrong_currency",
        "unvalued",
        "stale_valuation",
        "replaying_state",
        "epoch_mismatch",
        "missing_timestamp",
        "missing_equity",
        "master_only",
        "mixed_missing",
    ],
)
def test_zero_does_not_turn_missing_or_unqualified_evidence_current(mutation):
    rows = [source()]
    controls = [FinancialReconciliationControl(DAY, 1, "COMPLETED", AT + timedelta(seconds=1))]
    records = None
    expected = 0
    if mutation == "missing_control":
        controls = []
    elif mutation in {
        "wrong_day",
        "wrong_epoch",
        "pending",
        "failed",
        "replay",
        "stale_control",
        "missing_control_time",
    }:
        controls = [
            FinancialReconciliationControl(
                DAY - timedelta(days=1) if mutation == "wrong_day" else DAY,
                0 if mutation == "wrong_epoch" else 1,
                {"pending": "PENDING", "failed": "FAILED", "replay": "REQUIRES_REPLAY"}.get(
                    mutation, "COMPLETED"
                ),
                None
                if mutation == "missing_control_time"
                else (AT - timedelta(seconds=1) if mutation == "stale_control" else AT),
            )
        ]
    elif mutation == "old_snapshot":
        rows[0].snapshot.date -= timedelta(days=1)
    elif mutation in {
        "missing_value",
        "missing_local",
        "missing_currency",
        "wrong_currency",
        "unvalued",
        "stale_valuation",
        "missing_timestamp",
    }:
        field, value = {
            "missing_value": ("market_value", None),
            "missing_local": ("market_value_local", None),
            "missing_currency": ("valuation_source_currency", None),
            "wrong_currency": ("valuation_reporting_currency", "SGD"),
            "unvalued": ("valuation_status", "UNVALUED"),
            "stale_valuation": ("valuation_status", "VALUED_STALE"),
            "missing_timestamp": ("updated_at", None),
        }[mutation]
        setattr(rows[0].snapshot, field, value)
        if mutation == "missing_timestamp":
            rows[0].snapshot.created_at = None
            rows[0].instrument.created_at = rows[0].instrument.updated_at = None
    elif mutation == "replaying_state":
        rows[0].position_state.status = "REPLAYING"
    elif mutation == "epoch_mismatch":
        rows[0].position_state.epoch = 2
    elif mutation == "missing_equity":
        expected = 1
    elif mutation == "master_only":
        rows = []
    elif mutation == "mixed_missing":
        records = [
            SimpleNamespace(
                security_id=security,
                account_currency="USD",
                cash_account_id_source="cash_account_master",
            )
            for security in ("CASH_USD", "MISSING_CASH")
        ]
    result = qualify(rows, controls=controls, records=records, expected=expected)
    assert result.data_quality_status != "COMPLETE"
    assert not result.source_evidence_current


def test_material_epoch_control_and_valuation_change_identity_but_bookkeeping_does_not():
    row = source()
    before = qualify([row])
    row.position_state.updated_at += timedelta(days=1)
    assert qualify([row]).content_hash == before.content_hash
    row.snapshot.epoch = row.position_state.epoch = 2
    after = qualify(
        [row],
        controls=[FinancialReconciliationControl(DAY, 2, "COMPLETED", AT + timedelta(seconds=1))],
    )
    assert after.source_evidence_current
    assert after.content_hash != before.content_hash
    assert qualify([row], controls=[]).content_hash != after.content_hash
    row.snapshot.valuation_status = "UNVALUED"
    assert qualify([row], controls=[]).content_hash != qualify([source()], controls=[]).content_hash


def test_foreign_cash_requires_persisted_dated_fx_lineage():
    row = source()
    row.snapshot.valuation_source_currency = "SGD"
    records = [
        SimpleNamespace(
            security_id="CASH_USD",
            account_currency="SGD",
            cash_account_id_source="cash_account_master",
        )
    ]
    assert not qualify([row], records=records).source_evidence_current
    row.snapshot.valuation_fx_rate = Decimal("0.75")
    row.snapshot.valuation_fx_rate_date = DAY
    assert qualify([row], records=records).source_evidence_current


def test_all_controls_are_material_and_query_order_cannot_restate_identity():
    controls = [
        FinancialReconciliationControl(DAY, 1, "COMPLETED", AT + timedelta(seconds=1)),
        FinancialReconciliationControl(DAY, 1, "FAILED", AT + timedelta(seconds=2)),
    ]
    result = qualify([source()], controls=controls)
    assert result.reconciliation_status == result.data_quality_status == "BLOCKED"
    assert not result.source_evidence_current
    assert (
        qualify([source()], controls=list(reversed(controls))).content_hash == result.content_hash
    )
