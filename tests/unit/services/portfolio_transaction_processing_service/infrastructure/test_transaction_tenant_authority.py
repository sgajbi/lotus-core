"""Tests for durable transaction tenant resolution."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    transaction_tenant_authority as authority_contract,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    transaction_tenant_authority as authority_adapter,
)

pytestmark = pytest.mark.asyncio


def _authority(
    source_tenant_id: str | None,
) -> authority_adapter.SqlAlchemyTransactionTenantAuthority:
    result = MagicMock()
    result.scalar_one_or_none.return_value = source_tenant_id
    session = AsyncMock()
    session.execute.return_value = result
    session.__aenter__.return_value = session
    return authority_adapter.SqlAlchemyTransactionTenantAuthority(MagicMock(return_value=session))


async def test_resolve_accepts_legacy_event_without_asserted_tenant() -> None:
    authority = _authority(" tenant-a ")

    assert await authority.resolve(portfolio_id="PORT-1", asserted_tenant_id=None) == "tenant-a"


async def test_resolve_rejects_asserted_tenant_that_does_not_own_portfolio() -> None:
    authority = _authority("tenant-a")

    with pytest.raises(authority_contract.TransactionTenantAuthorityMismatch, match="does not own"):
        await authority.resolve(
            portfolio_id="PORT-1",
            asserted_tenant_id="tenant-b",
        )


async def test_resolve_retries_when_portfolio_authority_is_not_yet_durable() -> None:
    authority = _authority(None)

    with pytest.raises(
        authority_contract.TransactionTenantAuthorityUnavailable,
        match="no durable tenant",
    ):
        await authority.resolve(portfolio_id="PORT-1", asserted_tenant_id=None)
