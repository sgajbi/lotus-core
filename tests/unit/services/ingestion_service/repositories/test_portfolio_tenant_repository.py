from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.repositories.portfolio_tenant_repository import (
    SqlAlchemyPortfolioTenantReader,
)


@pytest.mark.asyncio
async def test_resolve_ownership_classifies_existing_and_tenant_owned_ids() -> None:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(portfolio_id="P-OWNED", tenant_id="tenant-a"),
        SimpleNamespace(portfolio_id="P-OTHER", tenant_id="tenant-b"),
    ]
    db.execute.return_value = result
    reader = SqlAlchemyPortfolioTenantReader(db)

    ownership = await reader.resolve_ownership(
        tenant_id="tenant-a",
        portfolio_ids={"P-OWNED", "P-OTHER", "P-MISSING"},
    )

    assert ownership.existing_ids == frozenset({"P-OWNED", "P-OTHER"})
    assert ownership.owned_ids == frozenset({"P-OWNED"})
    statement = db.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolios.portfolio_id IN" in compiled
    assert "portfolios.tenant_id" in compiled


@pytest.mark.asyncio
async def test_resolve_ownership_skips_database_for_empty_scope() -> None:
    db = AsyncMock(spec=AsyncSession)
    reader = SqlAlchemyPortfolioTenantReader(db)

    ownership = await reader.resolve_ownership(tenant_id="tenant-a", portfolio_ids=set())

    assert ownership.existing_ids == frozenset()
    assert ownership.owned_ids == frozenset()
    db.execute.assert_not_awaited()
