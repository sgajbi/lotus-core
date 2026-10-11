"""Source-cohort authority is independent of display eligibility and stored controls."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.application.holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationEvidence,
    holdings_reconciliation_evidence_hash,
    holdings_reconciliation_evidence_scopes,
    holdings_reconciliation_status,
    is_qualified_closed_cohort,
)

DAY = date(2025, 12, 31)
FACT = datetime(2026, 1, 1, tzinfo=UTC)


def _evidence(epoch: int, quantity: str) -> HoldingsReconciliationEvidence:
    return HoldingsReconciliationEvidence(
        history=SimpleNamespace(
            position_date=DAY, epoch=epoch, quantity=Decimal(quantity), updated_at=FACT
        ),
        snapshot=SimpleNamespace(
            date=DAY,
            epoch=epoch,
            quantity=Decimal(quantity),
            valuation_status="VALUED_CURRENT",
            market_value=Decimal("0"),
            market_value_local=Decimal("0"),
            valuation_source_currency="USD",
            valuation_reporting_currency="USD",
            updated_at=FACT,
        ),
        instrument=SimpleNamespace(currency="USD", updated_at=FACT),
        state=SimpleNamespace(epoch=epoch, status="CURRENT", updated_at=FACT),
        portfolio_currency="USD",
    )


def _control(epoch: int, status: str = "COMPLETED", seconds: int = 5):
    return FinancialReconciliationControl(DAY, epoch, status, FACT + timedelta(seconds=seconds))


def test_zero_cohort_selects_source_epoch_and_ignores_higher_stored_control():
    rows = [_evidence(0, "10"), _evidence(1, "0")]
    scopes = holdings_reconciliation_evidence_scopes(rows)
    assert [
        (scope.business_date, scope.epoch, scope.source_row_count) for scope in scopes.items
    ] == [(DAY, 1, 2)]
    assert (
        holdings_reconciliation_status(scopes=scopes, controls=[_control(0), _control(2)])
        == "UNRECONCILED"
    )
    assert holdings_reconciliation_status(scopes=scopes, controls=[_control(1)]) == "COMPLETE"


@pytest.mark.parametrize(
    "mutation",
    [
        "no_snapshot",
        "no_history",
        "no_state",
        "no_instrument",
        "state_epoch",
        "snapshot_epoch",
        "snapshot_quantity",
        "snapshot_date",
        "unvalued",
        "missing_value",
        "nonzero_value",
        "currency",
        "replaying",
    ],
)
def test_invalid_scope_only_member_fails_closed(mutation):
    row = _evidence(1, "0")
    if mutation.startswith("no_"):
        row = replace(row, **{mutation.removeprefix("no_"): None})
    elif mutation == "state_epoch":
        row.state.epoch = 2
    elif mutation == "snapshot_epoch":
        row.snapshot.epoch = 0
    elif mutation == "snapshot_quantity":
        row.snapshot.quantity = Decimal("1")
    elif mutation == "snapshot_date":
        row.snapshot.date = DAY - timedelta(days=1)
    elif mutation == "unvalued":
        row.snapshot.valuation_status = "PENDING"
    elif mutation == "missing_value":
        row.snapshot.market_value_local = None
    elif mutation == "nonzero_value":
        row.snapshot.market_value = Decimal("1")
    elif mutation == "currency":
        row.snapshot.valuation_source_currency = None
    elif mutation == "replaying":
        row.state.status = "REPROCESSING"
    scopes = holdings_reconciliation_evidence_scopes([_evidence(0, "10"), row])
    assert scopes.unscoped_source_row_count == 1
    assert (
        holdings_reconciliation_status(scopes=scopes, controls=[_control(0), _control(1)])
        == "UNKNOWN"
    )


@pytest.mark.parametrize(
    "status,expected", [("FAILED", "BLOCKED"), ("PENDING", "PARTIAL"), ("UNKNOWN", "UNKNOWN")]
)
def test_zero_cohort_preserves_adverse_control(status, expected):
    scopes = holdings_reconciliation_evidence_scopes([_evidence(1, "0")])
    assert holdings_reconciliation_status(scopes=scopes, controls=[_control(1, status)]) == expected


def test_zero_economic_changes_bind_identity_but_completion_bookkeeping_does_not():
    row = _evidence(1, "0")
    original = holdings_reconciliation_evidence_scopes([row])
    row.state.updated_at = FACT + timedelta(days=2)
    assert holdings_reconciliation_evidence_scopes([row]).content_hash() == original.content_hash()
    row.snapshot.updated_at = FACT + timedelta(seconds=10)
    changed = holdings_reconciliation_evidence_scopes([row])
    assert changed.content_hash() != original.content_hash()
    assert holdings_reconciliation_status(scopes=changed, controls=[_control(1)]) == "STALE"


def test_cohort_order_does_not_change_identity():
    rows = [_evidence(0, "10"), _evidence(1, "0")]
    assert (
        holdings_reconciliation_evidence_scopes(rows).content_hash()
        == holdings_reconciliation_evidence_scopes(rows[::-1]).content_hash()
    )


def test_full_evidence_identity_binds_invalid_changes_and_ignores_completion_clocks():
    rows = [_evidence(0, "10"), _evidence(1, "0")]

    def fingerprint():
        return holdings_reconciliation_evidence_hash(
            rows, holdings_reconciliation_evidence_scopes(rows)
        )

    original = fingerprint()
    rows.reverse()
    assert fingerprint() == original
    rows[0].state.updated_at = FACT + timedelta(days=3)
    assert fingerprint() == original
    rows[0].snapshot.valuation_status = "PENDING"
    invalid = fingerprint()
    assert invalid != original
    rows[0].snapshot.market_value = Decimal("1")
    assert fingerprint() != invalid


@pytest.mark.parametrize(
    "mutation",
    [
        "owner_currency",
        "source_currency",
        "target_currency",
        "missing_fx",
        "stale_fx",
        "zero_fx",
        "nonfinite_fx",
    ],
)
def test_zero_currency_and_dated_fx_authority_is_required(mutation):
    row = _evidence(1, "0")
    row.instrument.currency = "EUR"
    row.snapshot.valuation_source_currency = "EUR"
    row.snapshot.valuation_fx_rate = Decimal("1.1")
    row.snapshot.valuation_fx_rate_date = DAY
    if mutation == "owner_currency":
        row = replace(row, portfolio_currency=None)
    elif mutation == "source_currency":
        row.snapshot.valuation_source_currency = "SGD"
    elif mutation == "target_currency":
        row.snapshot.valuation_reporting_currency = "SGD"
    elif mutation == "missing_fx":
        row.snapshot.valuation_fx_rate = None
    elif mutation == "stale_fx":
        row.snapshot.valuation_fx_rate_date = DAY - timedelta(days=1)
    else:
        row.snapshot.valuation_fx_rate = Decimal("0" if mutation == "zero_fx" else "NaN")
    assert holdings_reconciliation_evidence_scopes([row]).unscoped_source_row_count == 1


def test_observed_closed_cohort_requires_valid_sources_not_empty_presence():
    rows = [_evidence(1, "0")]
    assert is_qualified_closed_cohort(rows, holdings_reconciliation_evidence_scopes(rows))
    assert not is_qualified_closed_cohort([], holdings_reconciliation_evidence_scopes([]))
    rows.append(_evidence(0, "10"))
    assert not is_qualified_closed_cohort(rows, holdings_reconciliation_evidence_scopes(rows))
    rows = [replace(_evidence(1, "0"), snapshot=None)]
    assert not is_qualified_closed_cohort(rows, holdings_reconciliation_evidence_scopes(rows))


def test_zero_cohort_accepts_persisted_same_date_positive_fx():
    row = _evidence(1, "0")
    row.instrument.currency = "EUR"
    row.snapshot.valuation_source_currency = "EUR"
    row.snapshot.valuation_fx_rate = Decimal("1.1")
    row.snapshot.valuation_fx_rate_date = DAY
    scopes = holdings_reconciliation_evidence_scopes([row])
    assert scopes.unscoped_source_row_count == 0
    assert holdings_reconciliation_status(scopes=scopes, controls=[_control(1)]) == "COMPLETE"


@pytest.mark.parametrize("field", ["source", "reporting", "instrument", "portfolio"])
def test_malformed_persisted_zero_currency_fails_closed(field):
    row = _evidence(1, "0")
    if field == "source":
        row.snapshot.valuation_source_currency = "US1"
    elif field == "reporting":
        row.snapshot.valuation_reporting_currency = "US1"
    elif field == "instrument":
        row.instrument.currency = "US1"
    else:
        row = replace(row, portfolio_currency="US1")
    rows = [_evidence(0, "10"), row]
    scopes = holdings_reconciliation_evidence_scopes(rows)
    assert scopes.unscoped_source_row_count == 1
    assert (
        holdings_reconciliation_status(scopes=scopes, controls=[_control(0), _control(1)])
        == "UNKNOWN"
    )
    assert not is_qualified_closed_cohort(rows, scopes)


def test_portfolio_reference_correction_dates_scope_and_material_identity():
    row = _evidence(1, "0")
    original_scopes = holdings_reconciliation_evidence_scopes([row])
    original_hash = holdings_reconciliation_evidence_hash([row], original_scopes)
    corrected_at = FACT + timedelta(seconds=10)
    corrected = replace(row, portfolio_evidence_timestamp=corrected_at)
    scopes = holdings_reconciliation_evidence_scopes([corrected])
    assert scopes.items[0].latest_evidence_timestamp == corrected_at
    assert holdings_reconciliation_status(scopes=scopes, controls=[_control(1)]) == "STALE"
    assert holdings_reconciliation_evidence_hash([corrected], scopes) != original_hash
    assert (
        holdings_reconciliation_status(scopes=scopes, controls=[_control(1, seconds=20)])
        == "COMPLETE"
    )
