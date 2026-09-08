from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.services.portfolio_validation import ensure_portfolio_exists
from tests.test_support.tenant import TEST_TENANT_CONTEXT

pytestmark = pytest.mark.asyncio


async def test_ensure_portfolio_exists_allows_known_portfolio() -> None:
    repository = AsyncMock()
    repository.portfolio_exists.return_value = True

    await ensure_portfolio_exists(
        repository=repository, portfolio_id="P1", tenant_id=TEST_TENANT_CONTEXT.tenant_id
    )

    repository.portfolio_exists.assert_awaited_once_with(
        "P1", tenant_id=TEST_TENANT_CONTEXT.tenant_id
    )


async def test_ensure_portfolio_exists_raises_lookup_error_for_missing_portfolio() -> None:
    repository = AsyncMock()
    repository.portfolio_exists.return_value = False

    with pytest.raises(LookupError, match="Portfolio with id P404 not found"):
        await ensure_portfolio_exists(
            repository=repository, portfolio_id="P404", tenant_id=TEST_TENANT_CONTEXT.tenant_id
        )

    repository.portfolio_exists.assert_awaited_once_with(
        "P404", tenant_id=TEST_TENANT_CONTEXT.tenant_id
    )


async def test_ensure_portfolio_exists_requires_a_tenant() -> None:
    """The gate cannot be called without one.

    This helper guards eleven routes across six services. A default tenant would
    have let any call site keep asking "does this portfolio exist anywhere",
    which is the question that admitted foreign portfolios in the first place.
    """
    repository = AsyncMock()
    repository.portfolio_exists.return_value = True

    with pytest.raises(TypeError):
        await ensure_portfolio_exists(repository=repository, portfolio_id="P1")  # type: ignore[call-arg]


async def test_a_foreign_portfolio_is_reported_exactly_as_an_absent_one() -> None:
    """Rule from tranche A, now enforced by the shared gate.

    A distinguishable refusal would confirm that an identifier the caller cannot
    read is real, which is the enumeration oracle the contract forbids.
    """
    repository = AsyncMock()
    repository.portfolio_exists.return_value = False

    with pytest.raises(LookupError) as absent:
        await ensure_portfolio_exists(
            repository=repository, portfolio_id="P1", tenant_id=TEST_TENANT_CONTEXT.tenant_id
        )

    assert str(absent.value) == "Portfolio with id P1 not found"
