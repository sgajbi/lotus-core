from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    PositionHistory,
    PositionState,
)

from src.services.query_service.app.application.holdings_reconciliation import (
    FinancialReconciliationControl,
)
from src.services.query_service.app.services.position_holdings_response import (
    portfolio_holdings_response,
)

pytestmark = pytest.mark.asyncio


async def test_portfolio_holdings_response_assembles_snapshot_holdings() -> None:
    repository = AsyncMock()
    snapshot = DailyPositionSnapshot(
        security_id=" SEC_A ",
        quantity=Decimal("100"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
        market_price=Decimal("10"),
        market_value=Decimal("1000"),
        market_value_local=Decimal("1000"),
        unrealized_gain_loss=Decimal("0"),
        unrealized_gain_loss_local=Decimal("0"),
        valuation_source_currency="USD",
        valuation_reporting_currency="USD",
        date=date(2025, 1, 1),
        epoch=7,
        created_at=datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
    )
    instrument = Instrument(
        name="Security A",
        asset_class="Equity",
        currency="USD",
        product_type="Equity",
    )
    state = PositionState(
        status="CURRENT",
        epoch=7,
        updated_at=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
    )
    repository.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (snapshot, instrument, state)
    ]
    repository.get_latest_position_history_by_portfolio_as_of_date.return_value = []
    repository.get_latest_snapshot_valuation_map_as_of_date.return_value = {}
    repository.get_held_since_dates.return_value = {("SEC_A", 7): date(2024, 12, 31)}
    repository.get_latest_market_price_dates.return_value = {"SEC_A": date(2025, 1, 1)}
    repository.get_holdings_reconciliation_controls.return_value = [
        FinancialReconciliationControl(
            business_date=date(2025, 1, 1),
            epoch=7,
            status="COMPLETED",
            updated_at=datetime(2025, 1, 1, 10, 6, tzinfo=UTC),
        )
    ]

    response = await portfolio_holdings_response(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 1),
    )

    repository.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
        "P1", date(2025, 1, 1)
    )
    repository.get_latest_position_history_by_portfolio_as_of_date.assert_awaited_once_with(
        "P1", date(2025, 1, 1)
    )
    repository.get_latest_snapshot_valuation_map_as_of_date.assert_not_awaited()
    repository.get_held_since_dates.assert_awaited_once_with(
        portfolio_id="P1",
        security_epoch_pairs=[("SEC_A", 7)],
    )
    repository.get_latest_market_price_dates.assert_awaited_once_with(
        security_ids=["SEC_A"],
        as_of_date=date(2025, 1, 1),
    )
    assert response.portfolio_id == "P1"
    assert response.as_of_date == date(2025, 1, 1)
    assert response.data_quality_status == "COMPLETE"
    assert response.reconciliation_status == "COMPLETE"
    assert response.freshness_status == "CURRENT"
    assert response.source_evidence_current is True
    assert response.snapshot_id is not None
    assert response.policy_version == "holdings-as-of-v1"
    assert response.latest_evidence_timestamp == datetime(2025, 1, 1, 10, 5, tzinfo=UTC)
    assert response.source_batch_fingerprint is None
    assert response.content_hash.startswith("sha256:")
    assert response.source_digest == response.content_hash
    assert response.source_refs == ["lotus-core://source/HoldingsAsOf/P1/2025-01-01"]
    assert response.source_lineage["source_product"] == "HoldingsAsOf"
    assert response.source_lineage["reconstruction_scope_id"].startswith("rs_")
    assert response.source_lineage["reconstruction_restatement_version"] == "current"
    assert response.degradation.status == "NONE"
    assert len(response.positions) == 1
    assert response.positions[0].security_id == "SEC_A"
    assert response.positions[0].weight == Decimal("1")
    assert response.positions[0].held_since_date == date(2024, 12, 31)


async def test_portfolio_holdings_response_marks_prior_date_fx_evidence_stale() -> None:
    repository = AsyncMock()
    snapshot = DailyPositionSnapshot(
        security_id="FX_A",
        quantity=Decimal("100"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("800"),
        market_price=Decimal("10"),
        market_value=Decimal("1000"),
        market_value_local=Decimal("800"),
        valuation_fx_rate=Decimal("1.25"),
        valuation_fx_rate_date=date(2025, 1, 1),
        valuation_source_currency="USD",
        valuation_reporting_currency="CHF",
        date=date(2025, 1, 2),
        epoch=7,
        updated_at=datetime(2025, 1, 2, 10, 0, tzinfo=UTC),
    )
    instrument = Instrument(
        name="Cross-currency security",
        asset_class="Equity",
        currency="USD",
    )
    state = PositionState(
        status="CURRENT",
        epoch=7,
        updated_at=datetime(2025, 1, 2, 10, 5, tzinfo=UTC),
    )
    repository.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (snapshot, instrument, state)
    ]
    repository.get_latest_position_history_by_portfolio_as_of_date.return_value = []
    repository.get_held_since_dates.return_value = {("FX_A", 7): date(2024, 12, 31)}
    repository.get_latest_market_price_dates.return_value = {"FX_A": date(2025, 1, 2)}
    repository.get_holdings_reconciliation_controls.return_value = [
        FinancialReconciliationControl(
            business_date=date(2025, 1, 2),
            epoch=7,
            status="COMPLETED",
            updated_at=datetime(2025, 1, 2, 10, 6, tzinfo=UTC),
        )
    ]

    response = await portfolio_holdings_response(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 2),
    )

    assert response.data_quality_status == "STALE"
    assert response.freshness_status == "STALE"
    assert response.source_evidence_current is False
    assert response.degradation.status == "STALE"
    assert response.degradation.reason_codes == ["FX_RATE_STALE"]
    detail = response.degradation.details[0]
    assert detail.record_key == "security_id:FX_A"
    assert detail.source_as_of_date == date(2025, 1, 1)
    assert detail.freshness_status == "STALE"


async def test_portfolio_holdings_response_fails_closed_for_legacy_currency_lineage() -> None:
    repository = AsyncMock()
    snapshot = DailyPositionSnapshot(
        security_id="LEGACY_A",
        quantity=Decimal("100"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("800"),
        market_price=Decimal("10"),
        market_value=Decimal("1000"),
        market_value_local=Decimal("800"),
        date=date(2025, 1, 2),
        epoch=7,
        updated_at=datetime(2025, 1, 2, 10, 0, tzinfo=UTC),
    )
    instrument = Instrument(
        name="Legacy security",
        asset_class="Equity",
        currency="USD",
    )
    state = PositionState(
        status="CURRENT",
        epoch=7,
        updated_at=datetime(2025, 1, 2, 10, 5, tzinfo=UTC),
    )
    repository.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (snapshot, instrument, state)
    ]
    repository.get_latest_position_history_by_portfolio_as_of_date.return_value = []
    repository.get_held_since_dates.return_value = {("LEGACY_A", 7): date(2024, 12, 31)}
    repository.get_latest_market_price_dates.return_value = {"LEGACY_A": date(2025, 1, 2)}
    repository.get_holdings_reconciliation_controls.return_value = [
        FinancialReconciliationControl(
            business_date=date(2025, 1, 2),
            epoch=7,
            status="COMPLETED",
            updated_at=datetime(2025, 1, 2, 10, 6, tzinfo=UTC),
        )
    ]

    response = await portfolio_holdings_response(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 2),
    )

    assert response.data_quality_status == "UNKNOWN"
    assert response.freshness_status == "UNAVAILABLE"
    assert response.source_evidence_current is False
    assert response.degradation.status == "UNKNOWN"
    assert response.degradation.reason_codes == ["VALUATION_CURRENCY_LINEAGE_MISSING"]
    detail = response.degradation.details[0]
    assert detail.record_key == "security_id:LEGACY_A"
    assert detail.source_kind == "UNAVAILABLE"
    assert detail.source_as_of_date is None
    assert detail.affected_fields == [
        "valuation.market_value",
        "valuation.unrealized_gain_loss",
        "valuation.unrealized_price_gain_loss",
        "valuation.unrealized_fx_gain_loss",
    ]


async def test_portfolio_holdings_response_exposes_fallback_degradation_metadata() -> None:
    repository = AsyncMock()
    history = PositionHistory(
        security_id=" HIST_A ",
        quantity=Decimal("20"),
        cost_basis=Decimal("200"),
        cost_basis_local=Decimal("198"),
        position_date=date(2025, 1, 1),
        epoch=3,
        updated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
    )
    instrument = Instrument(name="History A", asset_class="Equity", currency="USD")
    state = PositionState(
        status="CURRENT",
        epoch=3,
        updated_at=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
    )
    repository.get_latest_positions_by_portfolio_as_of_date.return_value = []
    repository.get_latest_position_history_by_portfolio_as_of_date.return_value = [
        (history, instrument, state)
    ]
    repository.get_latest_snapshot_valuation_map_as_of_date.return_value = {
        "HIST_A": {
            "market_price": Decimal("11"),
            "market_value": Decimal("220"),
            "unrealized_gain_loss": Decimal("20"),
            "market_value_local": Decimal("218"),
            "unrealized_gain_loss_local": Decimal("20"),
            "valuation_source_currency": "USD",
            "valuation_reporting_currency": "USD",
        }
    }
    repository.get_held_since_dates.return_value = {("HIST_A", 3): date(2024, 12, 1)}
    repository.get_latest_market_price_dates.return_value = {"HIST_A": date(2025, 1, 1)}
    repository.get_holdings_reconciliation_controls.return_value = []

    response = await portfolio_holdings_response(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 1),
    )

    assert response.data_quality_status == "UNKNOWN"
    assert response.reconciliation_status == "UNRECONCILED"
    assert response.freshness_status == "UNAVAILABLE"
    assert response.source_evidence_current is False
    assert response.source_batch_fingerprint is None
    assert response.degradation.status == "PARTIAL"
    assert response.degradation.reason_codes == ["HOLDINGS_VALUATION_FALLBACK"]
    assert response.degradation.details[0].record_key == "security_id:HIST_A"
    assert response.degradation.details[0].source_kind == "FALLBACK"


async def test_portfolio_holdings_response_preserves_unknown_for_fallback_missing_lineage() -> None:
    repository = AsyncMock()
    history = PositionHistory(
        security_id="HIST_LEGACY",
        quantity=Decimal("20"),
        cost_basis=Decimal("200"),
        cost_basis_local=Decimal("198"),
        position_date=date(2025, 1, 1),
        epoch=3,
        updated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
    )
    instrument = Instrument(name="Legacy history", asset_class="Equity", currency="USD")
    state = PositionState(
        status="CURRENT",
        epoch=3,
        updated_at=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
    )
    repository.get_latest_positions_by_portfolio_as_of_date.return_value = []
    repository.get_latest_position_history_by_portfolio_as_of_date.return_value = [
        (history, instrument, state)
    ]
    repository.get_latest_snapshot_valuation_map_as_of_date.return_value = {
        "HIST_LEGACY": {
            "market_price": Decimal("11"),
            "market_value": Decimal("220"),
            "unrealized_gain_loss": Decimal("20"),
            "market_value_local": Decimal("218"),
            "unrealized_gain_loss_local": Decimal("20"),
        }
    }
    repository.get_held_since_dates.return_value = {("HIST_LEGACY", 3): date(2024, 12, 1)}
    repository.get_latest_market_price_dates.return_value = {"HIST_LEGACY": date(2025, 1, 1)}
    repository.get_holdings_reconciliation_controls.return_value = [
        FinancialReconciliationControl(
            business_date=date(2025, 1, 1),
            epoch=3,
            status="COMPLETED",
            updated_at=datetime(2025, 1, 1, 10, 6, tzinfo=UTC),
        )
    ]

    response = await portfolio_holdings_response(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 1),
    )

    assert response.data_quality_status == "UNKNOWN"
    assert response.degradation.status == "UNKNOWN"
    assert response.degradation.reason_codes == [
        "HOLDINGS_VALUATION_FALLBACK",
        "VALUATION_CURRENCY_LINEAGE_MISSING",
    ]
    lineage_detail = next(
        detail
        for detail in response.degradation.details
        if detail.reason_code == "VALUATION_CURRENCY_LINEAGE_MISSING"
    )
    assert lineage_detail.record_key == "security_id:HIST_LEGACY"
    assert lineage_detail.freshness_status == "UNKNOWN"
