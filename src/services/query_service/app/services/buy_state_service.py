from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.buy_state_dto import (
    AccruedIncomeOffsetRecord,
    AccruedIncomeOffsetsResponse,
    BuyCashLinkageResponse,
    PositionLotRecord,
    PositionLotsResponse,
)
from ..repositories.buy_state_repository import BuyStateRepository


class BuyStateService:
    def __init__(self, db: AsyncSession):
        self.repo = BuyStateRepository(db)

    async def get_position_lots(
        self, portfolio_id: str, security_id: str
    ) -> PositionLotsResponse:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        lots = await self.repo.get_position_lots(portfolio_id=portfolio_id, security_id=security_id)
        if not lots:
            raise LookupError(
                f"BUY state not found for portfolio {portfolio_id} and security {security_id}"
            )
        return PositionLotsResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            lots=[PositionLotRecord.model_validate(lot) for lot in lots],
        )

    async def get_accrued_offsets(
        self, portfolio_id: str, security_id: str
    ) -> AccruedIncomeOffsetsResponse:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        offsets = await self.repo.get_accrued_offsets(portfolio_id=portfolio_id, security_id=security_id)
        if not offsets:
            raise LookupError(
                f"BUY state not found for portfolio {portfolio_id} and security {security_id}"
            )
        return AccruedIncomeOffsetsResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            offsets=[AccruedIncomeOffsetRecord.model_validate(offset) for offset in offsets],
        )

    async def get_buy_cash_linkage(
        self, portfolio_id: str, transaction_id: str
    ) -> BuyCashLinkageResponse:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        row = await self.repo.get_buy_cash_linkage(
            portfolio_id=portfolio_id, transaction_id=transaction_id
        )
        if row is None:
            raise LookupError(
                f"BUY cash linkage not found for portfolio {portfolio_id} and transaction "
                f"{transaction_id}"
            )
        txn, cashflow = row
        return BuyCashLinkageResponse(
            portfolio_id=portfolio_id,
            transaction_id=txn.transaction_id,
            transaction_type=txn.transaction_type,
            economic_event_id=txn.economic_event_id,
            linked_transaction_group_id=txn.linked_transaction_group_id,
            cashflow_date=cashflow.cashflow_date if cashflow else None,
            cashflow_amount=cashflow.amount if cashflow else None,
            cashflow_currency=cashflow.currency if cashflow else None,
            cashflow_classification=cashflow.classification if cashflow else None,
        )
