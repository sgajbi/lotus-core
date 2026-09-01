from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from src.services.ingestion_service.app.infrastructure.portfolio_tenant_ownership_reader import (
    SqlAlchemyPortfolioTenantOwnershipReader,
)
from src.services.ingestion_service.app.ports.portfolio_tenant_ownership import (
    PortfolioTenantOwnershipReadError,
)

pytestmark = pytest.mark.asyncio


async def test_reader_returns_only_authoritatively_owned_portfolios() -> None:
    db = AsyncMock()
    rows = MagicMock()
    rows.all.return_value = ["PORT-1"]
    db.scalars.return_value = rows

    owned = await SqlAlchemyPortfolioTenantOwnershipReader(db).read_owned_portfolio_ids(
        tenant_id="tenant-a",
        portfolio_ids=("PORT-1", "PORT-2"),
    )

    assert owned == frozenset({"PORT-1"})
    statement = db.scalars.await_args.args[0]
    compiled = statement.compile()
    assert "portfolios.tenant_id" in str(compiled)
    assert "tenant-a" in compiled.params.values()


async def test_reader_fails_closed_when_portfolio_authority_is_unavailable() -> None:
    db = AsyncMock()
    db.scalars.side_effect = OperationalError("select", {}, RuntimeError("db unavailable"))

    with pytest.raises(PortfolioTenantOwnershipReadError, match="lookup is unavailable"):
        await SqlAlchemyPortfolioTenantOwnershipReader(db).read_owned_portfolio_ids(
            tenant_id="tenant-a",
            portfolio_ids=("PORT-1",),
        )
