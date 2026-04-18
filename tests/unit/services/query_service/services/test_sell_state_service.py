from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.query_service.app.services.sell_state_service import SellStateService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_sell_state_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.portfolio_exists.return_value = True
    repo.get_sell_disposals.return_value = [
        SimpleNamespace(
            transaction_id="TXN-SELL-1",
            transaction_date=datetime(2026, 3, 1, 9, 30),
            instrument_id="AAPL",
            security_id="US0378331005",
            quantity=Decimal("-25"),
            net_cost=Decimal("-3750"),
            net_cost_local=Decimal("-3750"),
            realized_gain_loss=Decimal("500"),
            realized_gain_loss_local=Decimal("500"),
            economic_event_id="EVT-SELL-PORT-1-TXN-SELL-1",
            linked_transaction_group_id="LTG-SELL-PORT-1-TXN-SELL-1",
            calculation_policy_id="SELL_FIFO_POLICY",
            calculation_policy_version="1.0.0",
            source_system="OMS_PRIMARY",
        )
    ]
    repo.get_sell_cash_linkage.return_value = (
        SimpleNamespace(
            transaction_id="TXN-SELL-1",
            transaction_type="SELL",
            economic_event_id="EVT-SELL-PORT-1-TXN-SELL-1",
            linked_transaction_group_id="LTG-SELL-PORT-1-TXN-SELL-1",
            calculation_policy_id="SELL_FIFO_POLICY",
            calculation_policy_version="1.0.0",
        ),
        SimpleNamespace(
            cashflow_date=datetime(2026, 3, 3, 0, 0),
            amount=Decimal("4250"),
            currency="USD",
            classification="INVESTMENT_INFLOW",
        ),
    )
    return repo


async def test_get_sell_disposals_maps_deterministic_fields(mock_sell_state_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        response = await service.get_sell_disposals("PORT-1", "US0378331005")

    assert len(response.sell_disposals) == 1
    record = response.sell_disposals[0]
    assert record.quantity_disposed == Decimal("25")
    assert record.disposal_cost_basis_base == Decimal("3750")
    assert record.net_sell_proceeds_base == Decimal("4250")
    assert record.realized_gain_loss_base == Decimal("500")
    assert record.calculation_policy_id == "SELL_FIFO_POLICY"


async def test_get_sell_cash_linkage_returns_sell_mapping(mock_sell_state_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        response = await service.get_sell_cash_linkage("PORT-1", "TXN-SELL-1")

    assert response.transaction_type == "SELL"
    assert response.cashflow_amount == Decimal("4250")
    assert response.cashflow_classification == "INVESTMENT_INFLOW"


async def test_get_sell_cash_linkage_raises_when_not_found(mock_sell_state_repo: AsyncMock):
    mock_sell_state_repo.get_sell_cash_linkage.return_value = None
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        with pytest.raises(
            LookupError,
            match="SELL cash linkage not found for portfolio PORT-1 and transaction TX404",
        ):
            await service.get_sell_cash_linkage("PORT-1", "TX404")


async def test_get_sell_disposals_raises_when_portfolio_missing(mock_sell_state_repo: AsyncMock):
    mock_sell_state_repo.portfolio_exists.return_value = False
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
            await service.get_sell_disposals("P404", "US0378331005")


async def test_get_sell_cash_linkage_raises_when_portfolio_missing(
    mock_sell_state_repo: AsyncMock,
):
    mock_sell_state_repo.portfolio_exists.return_value = False
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
            await service.get_sell_cash_linkage("P404", "TXN-SELL-1")


async def test_get_sell_disposals_maps_none_paths(mock_sell_state_repo: AsyncMock):
    mock_sell_state_repo.get_sell_disposals.return_value = [
        SimpleNamespace(
            transaction_id="TXN-SELL-2",
            transaction_date=datetime(2026, 3, 2, 9, 30),
            instrument_id="AAPL",
            security_id="US0378331005",
            quantity=Decimal("-1"),
            net_cost=None,
            net_cost_local=None,
            realized_gain_loss=None,
            realized_gain_loss_local=None,
            economic_event_id=None,
            linked_transaction_group_id=None,
            calculation_policy_id=None,
            calculation_policy_version=None,
            source_system=None,
        )
    ]
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        response = await service.get_sell_disposals("PORT-1", "US0378331005")

    record = response.sell_disposals[0]
    assert record.disposal_cost_basis_base is None
    assert record.net_sell_proceeds_base is None


async def test_get_sell_disposals_raises_when_security_has_no_sell_state(
    mock_sell_state_repo: AsyncMock,
):
    mock_sell_state_repo.get_sell_disposals.return_value = []
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        with pytest.raises(
            LookupError,
            match="SELL state not found for portfolio PORT-1 and security US0378331005",
        ):
            await service.get_sell_disposals("PORT-1", "US0378331005")


async def test_get_sell_disposals_preserves_independent_base_and_local_disposal_arithmetic(
    mock_sell_state_repo: AsyncMock,
):
    mock_sell_state_repo.get_sell_disposals.return_value = [
        SimpleNamespace(
            transaction_id="TXN-SELL-FX-1",
            transaction_date=datetime(2026, 3, 4, 9, 30),
            instrument_id="EUR_BOND_1",
            security_id="XS0000000001",
            quantity=Decimal("-10"),
            net_cost=Decimal("-1000"),
            net_cost_local=Decimal("-920"),
            realized_gain_loss=Decimal("80"),
            realized_gain_loss_local=Decimal("55"),
            economic_event_id="EVT-SELL-PORT-1-TXN-SELL-FX-1",
            linked_transaction_group_id="LTG-SELL-PORT-1-TXN-SELL-FX-1",
            calculation_policy_id="SELL_FIFO_POLICY",
            calculation_policy_version="1.0.0",
            source_system="OMS_PRIMARY",
        )
    ]
    with patch(
        "src.services.query_service.app.services.sell_state_service.SellStateRepository",
        return_value=mock_sell_state_repo,
    ):
        service = SellStateService(AsyncMock())
        response = await service.get_sell_disposals("PORT-1", "XS0000000001")

    record = response.sell_disposals[0]
    assert record.quantity_disposed == Decimal("10")
    assert record.disposal_cost_basis_base == Decimal("1000")
    assert record.disposal_cost_basis_local == Decimal("920")
    assert record.realized_gain_loss_base == Decimal("80")
    assert record.realized_gain_loss_local == Decimal("55")
    assert record.net_sell_proceeds_base == Decimal("1080")
    assert record.net_sell_proceeds_local == Decimal("975")
