from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.cash_account_dto import CashAccountQueryResponse, CashAccountRecord
from ..repositories.cash_account_repository import CashAccountRepository


class CashAccountService:
    def __init__(self, db: AsyncSession):
        self.repo = CashAccountRepository(db)

    async def get_cash_accounts(
        self, portfolio_id: str, *, as_of_date: date | None = None
    ) -> CashAccountQueryResponse:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

        accounts = await self.repo.list_cash_accounts(portfolio_id, as_of_date=as_of_date)
        return CashAccountQueryResponse(
            portfolio_id=portfolio_id,
            resolved_as_of_date=as_of_date,
            cash_accounts=[CashAccountRecord.model_validate(account) for account in accounts],
        )
