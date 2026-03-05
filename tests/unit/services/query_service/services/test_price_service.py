# tests/unit/services/query_service/services/test_price_service.py
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import MarketPrice

from src.services.query_service.app.repositories.price_repository import MarketPriceRepository
from src.services.query_service.app.services.price_service import MarketPriceService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_price_repo() -> AsyncMock:
    """Provides a mock MarketPriceRepository."""
    repo = AsyncMock(spec=MarketPriceRepository)
    # FIX: Provide full, valid data for the mock object
    repo.get_prices.return_value = [
        MarketPrice(price_date=date(2025, 1, 1), price=Decimal("150.75"), currency="USD")
    ]
    return repo


async def test_get_prices(mock_price_repo: AsyncMock):
    """Tests the get_prices service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.price_service.MarketPriceRepository",
        return_value=mock_price_repo,
    ):
        service = MarketPriceService(AsyncMock())
        params = {
            "security_id": "S1",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 1, 31),
        }

        # ACT
        response = await service.get_prices(**params)

        # ASSERT
        mock_price_repo.get_prices.assert_awaited_once_with(**params)
        assert len(response.prices) == 1
        assert response.prices[0].price_date == date(2025, 1, 1)
        assert response.prices[0].price == Decimal("150.75")
