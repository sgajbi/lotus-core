# tests/unit/services/query_service/services/test_position_service.py
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    PositionHistory,
    PositionState,
)

from src.services.query_service.app.repositories.position_repository import PositionRepository
from src.services.query_service.app.services.position_service import PositionService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_position_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    repo.portfolio_exists.return_value = True

    mock_history_obj = PositionHistory(
        transaction_id="T1",
        position_date=date(2025, 1, 1),
        quantity=1,
        cost_basis=1,
        cost_basis_local=1,
    )
    repo.get_position_history_by_security.return_value = [(mock_history_obj, "CURRENT")]

    # --- FIX: Return the correct 3-tuple structure ---
    mock_snapshot = DailyPositionSnapshot(
        security_id="S1", quantity=Decimal(100), cost_basis=Decimal(1000), date=date(2025, 1, 1)
    )
    mock_instrument = Instrument(
        name="Test Instrument",
        isin="ISIN123",
        currency="USD",
        asset_class="Equity",
        product_type="Equity",
        sector="Technology",
        country_of_risk="US",
        rating="AA+",
        liquidity_tier="L2",
    )
    mock_state = PositionState(status="CURRENT", epoch=1)

    repo.get_latest_positions_by_portfolio.return_value = [
        (mock_snapshot, mock_instrument, mock_state)
    ]
    repo.get_latest_business_date.return_value = date(2025, 1, 1)
    repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (mock_snapshot, mock_instrument, mock_state)
    ]
    repo.get_held_since_dates.return_value = {("S1", 1): date(2024, 12, 31)}
    repo.get_latest_position_history_by_portfolio.return_value = []
    repo.get_latest_position_history_by_portfolio_as_of_date.return_value = []
    repo.get_latest_snapshot_valuation_map.return_value = {}
    repo.get_latest_snapshot_valuation_map_as_of_date.return_value = {}
    # --- END FIX ---
    return repo


async def test_get_position_history(mock_position_repo: AsyncMock):
    """Tests the position history service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())
        params = {
            "portfolio_id": "P1",
            "security_id": "S1",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 1, 31),
        }

        # ACT
        response = await service.get_position_history(**params)

        # ASSERT
        mock_position_repo.get_position_history_by_security.assert_awaited_once_with(**params)
        assert len(response.positions) == 1
        assert response.positions[0].transaction_id == "T1"
        assert response.positions[0].valuation is None
        assert response.positions[0].reprocessing_status == "CURRENT"


async def test_get_latest_positions(mock_position_repo: AsyncMock):
    """Tests the latest portfolio positions service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())

        # ACT
        response = await service.get_portfolio_positions(portfolio_id="P1")

        # ASSERT
        mock_position_repo.get_latest_business_date.assert_awaited_once()
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
            "P1", date(2025, 1, 1)
        )
        assert len(response.positions) == 1
        assert response.positions[0].security_id == "S1"
        assert response.positions[0].instrument_name == "Test Instrument"
        assert response.positions[0].reprocessing_status == "CURRENT"
        assert response.positions[0].asset_class == "Equity"
        assert response.positions[0].isin == "ISIN123"
        assert response.positions[0].currency == "USD"
        assert response.positions[0].sector == "Technology"
        assert response.positions[0].country_of_risk == "US"
        assert response.positions[0].product_type == "Equity"
        assert response.positions[0].rating == "AA+"
        assert response.positions[0].liquidity_tier == "L2"
        assert response.positions[0].held_since_date == date(2024, 12, 31)
        assert response.positions[0].weight == Decimal("1")


async def test_get_latest_positions_falls_back_to_position_history(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = []
        mock_history_obj = PositionHistory(
            security_id="S2",
            quantity=Decimal("55"),
            cost_basis=Decimal("5500"),
            cost_basis_local=Decimal("5500"),
            position_date=date(2025, 1, 2),
            transaction_id="T2",
        )
        mock_instrument = Instrument(
            name="Fallback Instrument",
            isin="ISIN456",
            currency="USD",
            asset_class="Bond",
            product_type="Bond",
            sector="N/A",
            country_of_risk="US",
            rating="A",
            liquidity_tier="L3",
        )
        mock_state = PositionState(status="CURRENT", epoch=1)
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
            (mock_history_obj, mock_instrument, mock_state)
        ]
        mock_position_repo.get_held_since_dates.return_value = {("S2", 1): date(2024, 1, 1)}
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.return_value = {
            "S2": {
                "market_price": Decimal("101.5"),
                "market_value": Decimal("5582.5"),
                "unrealized_gain_loss": Decimal("82.5"),
                "market_value_local": Decimal("5582.5"),
                "unrealized_gain_loss_local": Decimal("82.5"),
            }
        }

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions(portfolio_id="P2")

        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
            "P2", date(2025, 1, 1)
        )
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.assert_awaited_once_with(
            "P2", date(2025, 1, 1)
        )
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.assert_awaited_once_with(
            "P2", date(2025, 1, 1)
        )
        assert len(response.positions) == 1
        assert response.positions[0].security_id == "S2"
        assert response.positions[0].position_date == date(2025, 1, 2)
        assert response.positions[0].instrument_name == "Fallback Instrument"
        assert response.positions[0].product_type == "Bond"
        assert response.positions[0].rating == "A"
        assert response.positions[0].liquidity_tier == "L3"
        assert response.positions[0].asset_class == "Bond"
        assert response.positions[0].valuation is not None
        assert response.positions[0].valuation.market_value == Decimal("5582.5")
        assert response.positions[0].held_since_date == date(2024, 1, 1)
        assert response.positions[0].weight == Decimal("1")


async def test_get_position_history_raises_when_portfolio_missing(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.portfolio_exists.return_value = False
        service = PositionService(AsyncMock())

        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_position_history(portfolio_id="P404", security_id="S1")


async def test_get_portfolio_positions_raises_when_portfolio_missing(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.portfolio_exists.return_value = False
        service = PositionService(AsyncMock())

        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_portfolio_positions("P404")


async def test_get_latest_positions_fallback_without_snapshot_valuation_uses_cost_basis(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = []
        mock_history_obj = PositionHistory(
            security_id="S9",
            quantity=Decimal("10"),
            cost_basis=Decimal("123.45"),
            cost_basis_local=Decimal("123.45"),
            position_date=date(2025, 1, 3),
            transaction_id="T9",
        )
        mock_instrument = Instrument(
            name="No Valuation",
            isin="ISIN999",
            currency="USD",
            asset_class="Equity",
            sector="Tech",
            country_of_risk="US",
        )
        mock_state = PositionState(status="CURRENT", epoch=1)
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
            (mock_history_obj, mock_instrument, mock_state)
        ]
        mock_position_repo.get_held_since_dates.return_value = {}
        mock_position_repo.get_latest_snapshot_valuation_map.return_value = {}

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P9")

        assert response.positions[0].valuation is not None
        assert response.positions[0].valuation.market_price is None
        assert response.positions[0].valuation.market_value == Decimal("123.45")
        assert response.positions[0].valuation.unrealized_gain_loss == Decimal("0")
        assert response.positions[0].held_since_date == date(2025, 1, 3)


async def test_get_latest_positions_supplements_missing_snapshot_rows_from_history(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        snapshot_row = DailyPositionSnapshot(
            security_id="SNAP_ONLY",
            quantity=Decimal("100"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
            market_price=Decimal("10"),
            market_value=Decimal("1000"),
            market_value_local=Decimal("1000"),
            unrealized_gain_loss=Decimal("0"),
            unrealized_gain_loss_local=Decimal("0"),
            date=date(2025, 1, 1),
        )
        history_row = PositionHistory(
            security_id="HIST_ONLY",
            quantity=Decimal("310"),
            cost_basis=Decimal("57195"),
            cost_basis_local=Decimal("57195"),
            position_date=date(2025, 1, 1),
            transaction_id="T-HIST",
        )
        instrument = Instrument(
            name="Apple Inc.",
            isin="US0378331005",
            currency="USD",
            asset_class="Equity",
            product_type="Equity",
            sector="Technology",
            country_of_risk="US",
            rating=None,
            liquidity_tier="L1",
        )
        state = PositionState(status="REPROCESSING", epoch=2)

        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
            (snapshot_row, instrument, state)
        ]
        mock_position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
            (snapshot_row, instrument, state),
            (history_row, instrument, state),
        ]
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.return_value = {
            "HIST_ONLY": {
                "market_price": Decimal("209.1627"),
                "market_value": Decimal("64840.437"),
                "unrealized_gain_loss": Decimal("7645.437"),
                "market_value_local": Decimal("64840.437"),
                "unrealized_gain_loss_local": Decimal("7645.437"),
            }
        }
        mock_position_repo.get_held_since_dates.return_value = {
            ("SNAP_ONLY", 2): date(2024, 12, 31),
            ("HIST_ONLY", 2): date(2024, 4, 3),
        }

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P1", as_of_date=date(2025, 1, 1))

        assert {position.security_id for position in response.positions} == {
            "SNAP_ONLY",
            "HIST_ONLY",
        }
        history_position = next(
            position for position in response.positions if position.security_id == "HIST_ONLY"
        )
        assert history_position.quantity == Decimal("310")
        assert history_position.position_date == date(2025, 1, 1)
        assert history_position.valuation is not None
        assert history_position.valuation.market_value == Decimal("64840.437")
        assert history_position.reprocessing_status == "REPROCESSING"
        mock_position_repo.get_latest_snapshot_valuation_map_as_of_date.assert_awaited_once_with(
            "P1", date(2025, 1, 1)
        )


async def test_get_latest_positions_include_projected_uses_unbounded_latest(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        service = PositionService(AsyncMock())

        await service.get_portfolio_positions(portfolio_id="P1", include_projected=True)

        mock_position_repo.get_latest_business_date.assert_not_awaited()
        mock_position_repo.get_latest_positions_by_portfolio.assert_awaited_once_with("P1")


async def test_get_latest_positions_defaults_to_today_when_business_date_absent(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        mock_position_repo.get_latest_business_date.return_value = None
        service = PositionService(AsyncMock())

        await service.get_portfolio_positions(portfolio_id="P1")

        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
            "P1", date.today()
        )


async def test_get_latest_positions_weight_zero_when_all_values_zero(mock_position_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        zero_snapshot = DailyPositionSnapshot(
            security_id="S0",
            quantity=Decimal("1"),
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
            market_value=Decimal("0"),
            market_value_local=Decimal("0"),
            unrealized_gain_loss=Decimal("0"),
            unrealized_gain_loss_local=Decimal("0"),
            date=date(2025, 1, 1),
        )
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
            (zero_snapshot, None, PositionState(status="CURRENT", epoch=1))
        ]
        mock_position_repo.get_held_since_dates.return_value = {}

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P1")

        assert len(response.positions) == 1
        assert response.positions[0].weight == Decimal(0)
        assert response.positions[0].held_since_date == date(2025, 1, 1)


async def test_get_latest_positions_uses_default_held_since_when_map_missing(
    mock_position_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo,
    ):
        snapshot = DailyPositionSnapshot(
            security_id="S3",
            quantity=Decimal("2"),
            cost_basis=Decimal("20"),
            cost_basis_local=Decimal("20"),
            market_value=Decimal("20"),
            market_value_local=Decimal("20"),
            unrealized_gain_loss=Decimal("0"),
            unrealized_gain_loss_local=Decimal("0"),
            date=date(2025, 1, 2),
        )
        mock_position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
            (snapshot, None, PositionState(status="CURRENT", epoch=3))
        ]
        mock_position_repo.get_held_since_dates.return_value = {}

        service = PositionService(AsyncMock())
        response = await service.get_portfolio_positions("P1")

        assert response.positions[0].held_since_date == date(2025, 1, 2)
