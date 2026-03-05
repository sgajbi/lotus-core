# tests/unit/services/query_service/services/test_fx_rate_service.py
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import FxRate

from src.services.query_service.app.repositories.fx_rate_repository import FxRateRepository
from src.services.query_service.app.services.fx_rate_service import FxRateService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_fx_rate_repo() -> AsyncMock:
    """Provides a mock FxRateRepository."""
    repo = AsyncMock(spec=FxRateRepository)
    # FIX: Provide full, valid data for the mock object
    repo.get_fx_rates.return_value = [
        FxRate(
            rate_date=date(2025, 1, 1), rate=Decimal("1.1"), from_currency="USD", to_currency="EUR"
        )
    ]
    return repo


async def test_get_fx_rates(mock_fx_rate_repo: AsyncMock):
    """Tests the get_fx_rates service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.fx_rate_service.FxRateRepository",
        return_value=mock_fx_rate_repo,
    ):
        service = FxRateService(AsyncMock())
        params = {
            "from_currency": "USD",
            "to_currency": "EUR",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 1, 31),
        }

        # ACT
        response = await service.get_fx_rates(**params)

        # ASSERT
        mock_fx_rate_repo.get_fx_rates.assert_awaited_once_with(**params)
        assert len(response.rates) == 1
        assert response.rates[0].rate_date == date(2025, 1, 1)
        assert response.rates[0].rate == Decimal("1.1")
