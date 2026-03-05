from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    Cashflow,
    PositionLotState,
    Transaction,
)

from src.services.query_service.app.repositories.buy_state_repository import BuyStateRepository
from src.services.query_service.app.services.buy_state_service import BuyStateService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_buy_state_repo() -> AsyncMock:
    repo = AsyncMock(spec=BuyStateRepository)
    repo.portfolio_exists.return_value = True
    repo.get_position_lots.return_value = [
        PositionLotState(
            lot_id="LOT-TXN-1",
            source_transaction_id="TXN-1",
            portfolio_id="PORT-1",
            instrument_id="AAPL",
            security_id="US0378331005",
            acquisition_date=date(2026, 2, 28),
            original_quantity=Decimal("100"),
            open_quantity=Decimal("100"),
            lot_cost_local=Decimal("15005.5"),
            lot_cost_base=Decimal("15005.5"),
            accrued_interest_paid_local=Decimal("0"),
        )
    ]
    repo.get_accrued_offsets.return_value = [
        AccruedIncomeOffsetState(
            offset_id="AIO-TXN-1",
            source_transaction_id="TXN-1",
            portfolio_id="PORT-1",
            instrument_id="AAPL",
            security_id="US0378331005",
            accrued_interest_paid_local=Decimal("1250"),
            remaining_offset_local=Decimal("1250"),
        )
    ]
    repo.get_buy_cash_linkage.return_value = (
        Transaction(
            transaction_id="TXN-1",
            portfolio_id="PORT-1",
            instrument_id="AAPL",
            security_id="US0378331005",
            transaction_type="BUY",
            quantity=Decimal("100"),
            price=Decimal("150"),
            gross_transaction_amount=Decimal("15000"),
            trade_currency="USD",
            currency="USD",
            transaction_date=datetime(2026, 2, 28, 0, 0, 0),
            economic_event_id="EVT-1",
            linked_transaction_group_id="LTG-1",
        ),
        Cashflow(
            transaction_id="TXN-1",
            portfolio_id="PORT-1",
            security_id="US0378331005",
            cashflow_date=date(2026, 2, 28),
            amount=Decimal("-15005.5"),
            currency="USD",
            classification="INVESTMENT_OUTFLOW",
            timing="BOD",
            calculation_type="NET",
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )
    return repo


async def test_get_position_lots(mock_buy_state_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.buy_state_service.BuyStateRepository",
        return_value=mock_buy_state_repo,
    ):
        service = BuyStateService(AsyncMock())
        response = await service.get_position_lots("PORT-1", "US0378331005")
        assert response.portfolio_id == "PORT-1"
        assert response.security_id == "US0378331005"
        assert len(response.lots) == 1
        assert response.lots[0].lot_id == "LOT-TXN-1"


async def test_get_buy_cash_linkage(mock_buy_state_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.buy_state_service.BuyStateRepository",
        return_value=mock_buy_state_repo,
    ):
        service = BuyStateService(AsyncMock())
        response = await service.get_buy_cash_linkage("PORT-1", "TXN-1")
        assert response.transaction_id == "TXN-1"
        assert response.economic_event_id == "EVT-1"
        assert response.cashflow_classification == "INVESTMENT_OUTFLOW"


async def test_get_position_lots_raises_when_portfolio_missing(mock_buy_state_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.buy_state_service.BuyStateRepository",
        return_value=mock_buy_state_repo,
    ):
        mock_buy_state_repo.portfolio_exists.return_value = False
        service = BuyStateService(AsyncMock())
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_position_lots("P404", "US0378331005")


async def test_get_accrued_offsets_success(mock_buy_state_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.buy_state_service.BuyStateRepository",
        return_value=mock_buy_state_repo,
    ):
        service = BuyStateService(AsyncMock())
        response = await service.get_accrued_offsets("PORT-1", "US0378331005")
        assert response.portfolio_id == "PORT-1"
        assert response.security_id == "US0378331005"
        assert len(response.offsets) == 1
        assert response.offsets[0].offset_id == "AIO-TXN-1"


async def test_get_accrued_offsets_raises_when_portfolio_missing(mock_buy_state_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.buy_state_service.BuyStateRepository",
        return_value=mock_buy_state_repo,
    ):
        mock_buy_state_repo.portfolio_exists.return_value = False
        service = BuyStateService(AsyncMock())
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_accrued_offsets("P404", "US0378331005")


async def test_get_buy_cash_linkage_raises_when_transaction_not_found(
    mock_buy_state_repo: AsyncMock,
):
    with patch(
        "src.services.query_service.app.services.buy_state_service.BuyStateRepository",
        return_value=mock_buy_state_repo,
    ):
        mock_buy_state_repo.get_buy_cash_linkage.return_value = None
        service = BuyStateService(AsyncMock())
        with pytest.raises(ValueError, match="Transaction TXN-404 not found for portfolio PORT-1"):
            await service.get_buy_cash_linkage("PORT-1", "TXN-404")
