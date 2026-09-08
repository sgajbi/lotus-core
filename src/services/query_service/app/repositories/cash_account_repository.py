from __future__ import annotations

from datetime import date

from portfolio_common.database_models import CashAccountMaster
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .portfolio_existence import portfolio_exists_for_tenant


class CashAccountRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def portfolio_exists(self, portfolio_id: str, *, tenant_id: TenantId) -> bool:
        """Whether the admitted tenant owns this portfolio.

        Delegates so the predicate lives in one place; see
        :mod:`portfolio_existence`.
        """
        return await portfolio_exists_for_tenant(self.db, portfolio_id, tenant_id=tenant_id)

    async def list_cash_accounts(
        self,
        portfolio_id: str,
        *,
        as_of_date: date | None = None,
    ) -> list[CashAccountMaster]:
        stmt = select(CashAccountMaster).where(CashAccountMaster.portfolio_id == portfolio_id)
        if as_of_date is not None:
            stmt = stmt.where(
                or_(
                    CashAccountMaster.opened_on.is_(None),
                    CashAccountMaster.opened_on <= as_of_date,
                ),
                or_(
                    CashAccountMaster.closed_on.is_(None),
                    CashAccountMaster.closed_on >= as_of_date,
                ),
            )
        stmt = stmt.order_by(
            CashAccountMaster.account_currency.asc(),
            CashAccountMaster.cash_account_id.asc(),
        )
        return list((await self.db.execute(stmt)).scalars().all())
