from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.services.portfolio_validation import ensure_portfolio_owned

pytestmark = pytest.mark.asyncio


async def test_ensure_portfolio_owned_allows_tenant_owned_portfolio() -> None:
    repository = AsyncMock()
    repository.portfolio_exists.return_value = True

    await ensure_portfolio_owned(repository=repository, tenant_id="tenant-a", portfolio_id="P1")

    repository.portfolio_exists.assert_awaited_once_with(tenant_id="tenant-a", portfolio_id="P1")


async def test_ensure_portfolio_owned_raises_source_safe_error_for_foreign_portfolio() -> None:
    repository = AsyncMock()
    repository.portfolio_exists.return_value = False

    with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
        await ensure_portfolio_owned(
            repository=repository,
            tenant_id="tenant-a",
            portfolio_id="P404",
        )

    repository.portfolio_exists.assert_awaited_once_with(
        tenant_id="tenant-a",
        portfolio_id="P404",
    )
