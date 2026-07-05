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
        date=date(2025, 1, 1),
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
    assert response.latest_evidence_timestamp == datetime(2025, 1, 1, 10, 5, tzinfo=UTC)
    assert response.source_batch_fingerprint == response.content_hash
    assert response.content_hash.startswith("sha256:")
    assert response.source_digest == response.content_hash
    assert response.source_refs == ["lotus-core://source/HoldingsAsOf/P1/2025-01-01"]
    assert response.source_lineage["source_product"] == "HoldingsAsOf"
    assert response.degradation.status == "NONE"
    assert len(response.positions) == 1
    assert response.positions[0].security_id == "SEC_A"
    assert response.positions[0].weight == Decimal("1")
    assert response.positions[0].held_since_date == date(2024, 12, 31)


async def test_portfolio_holdings_response_exposes_fallback_degradation_metadata() -> None:
    repository = AsyncMock()
    history = PositionHistory(
        security_id=" HIST_A ",
        quantity=Decimal("20"),
        cost_basis=Decimal("200"),
        cost_basis_local=Decimal("198"),
        position_date=date(2025, 1, 1),
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
        }
    }
    repository.get_held_since_dates.return_value = {("HIST_A", 3): date(2024, 12, 1)}
    repository.get_latest_market_price_dates.return_value = {"HIST_A": date(2025, 1, 1)}

    response = await portfolio_holdings_response(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 1),
    )

    assert response.data_quality_status == "PARTIAL"
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash
    assert response.degradation.status == "PARTIAL"
    assert response.degradation.reason_codes == ["HOLDINGS_VALUATION_FALLBACK"]
    assert response.degradation.details[0].record_key == "security_id:HIST_A"
    assert response.degradation.details[0].source_kind == "FALLBACK"
