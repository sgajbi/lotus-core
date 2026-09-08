"""One tenant-scoped portfolio-existence read, shared by every query repository.

Eight repositories previously carried their own copy of this statement, identical
apart from a local variable name and one missing ``LIMIT 1``. The tenant
predicate was absent from all eight, so the existence gate answered "does this
portfolio exist anywhere" when every caller needed "does it exist for the
admitted tenant" -- and a fix applied per repository would have had to be got
right eight times and kept right afterwards.

Keeping the statement in one place is what makes the predicate a property of the
service rather than of whichever repository a route happens to use.
"""

from __future__ import annotations

from portfolio_common.database_models import Portfolio
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def portfolio_exists_for_tenant(
    db: AsyncSession, portfolio_id: str, *, tenant_id: TenantId
) -> bool:
    """Whether the admitted tenant owns a portfolio with this identifier.

    A portfolio owned by another tenant is reported exactly as an absent one, so
    a caller cannot use the existence gate to learn that an identifier it may not
    read is real.
    """
    statement = (
        select(Portfolio.portfolio_id)
        .where(
            Portfolio.portfolio_id == portfolio_id,
            Portfolio.tenant_id == tenant_id.value,
        )
        .limit(1)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None
