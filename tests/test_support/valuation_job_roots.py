"""Explicit persisted authority for PostgreSQL valuation-job fixtures."""

from datetime import date
from typing import Iterable

from portfolio_common.database_models import Portfolio
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_valuation_portfolios(
    session: AsyncSession, portfolio_ids: Iterable[str], *, tenant_id: TenantId
) -> None:
    """Persist the declared exact roots before scheduling or concurrent claims."""
    if not isinstance(tenant_id, TenantId):
        raise TypeError("fixture authority must be an explicit TenantId")
    identities = sorted(set(portfolio_ids))
    existing = {
        row.portfolio_id: row.tenant_id
        for row in (
            await session.execute(select(Portfolio).where(Portfolio.portfolio_id.in_(identities)))
        ).scalars()
    }
    for portfolio_id in identities:
        if portfolio_id in existing:
            assert existing[portfolio_id] == tenant_id.value
            continue
        session.add(
            Portfolio(
                tenant_id=tenant_id.value,
                portfolio_id=portfolio_id,
                legal_book_id=f"BOOK-{portfolio_id}",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="moderate",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="Singapore",
                client_id=f"CLIENT-{portfolio_id}",
                status="ACTIVE",
            )
        )
    await session.commit()
