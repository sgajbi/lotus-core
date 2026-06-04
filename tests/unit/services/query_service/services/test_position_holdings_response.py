from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import DailyPositionSnapshot, Instrument, PositionState

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
    assert len(response.positions) == 1
    assert response.positions[0].security_id == "SEC_A"
    assert response.positions[0].weight == Decimal("1")
    assert response.positions[0].held_since_date == date(2024, 12, 31)
