from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.services.portfolio_validation import ensure_portfolio_exists

pytestmark = pytest.mark.asyncio


async def test_ensure_portfolio_exists_allows_known_portfolio() -> None:
    repository = AsyncMock()
    repository.portfolio_exists.return_value = True

    await ensure_portfolio_exists(repository=repository, portfolio_id="P1")

    repository.portfolio_exists.assert_awaited_once_with("P1")


async def test_ensure_portfolio_exists_raises_lookup_error_for_missing_portfolio() -> None:
    repository = AsyncMock()
    repository.portfolio_exists.return_value = False

    with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
        await ensure_portfolio_exists(repository=repository, portfolio_id="P404")

    repository.portfolio_exists.assert_awaited_once_with("P404")
