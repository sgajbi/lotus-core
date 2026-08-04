"""Read immutable lot-disposal receipts without transaction-family assumptions."""

from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    Portfolio,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class LotDisposalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        statement = (
            select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        )
        return (await self.db.execute(statement)).scalar_one_or_none() is not None

    async def get_latest_receipt(
        self,
        *,
        portfolio_id: str,
        transaction_id: str,
    ) -> tuple[LotDisposalReceiptRecord, list[LotDisposalAllocationRecord]] | None:
        latest_version = (
            select(func.max(LotDisposalReceiptRecord.receipt_version))
            .where(
                LotDisposalReceiptRecord.portfolio_id == portfolio_id,
                LotDisposalReceiptRecord.disposal_transaction_id == transaction_id,
            )
            .scalar_subquery()
        )
        statement = (
            select(LotDisposalReceiptRecord, LotDisposalAllocationRecord)
            .outerjoin(
                LotDisposalAllocationRecord,
                and_(
                    LotDisposalAllocationRecord.receipt_id == LotDisposalReceiptRecord.receipt_id,
                    LotDisposalAllocationRecord.receipt_version
                    == LotDisposalReceiptRecord.receipt_version,
                    LotDisposalAllocationRecord.portfolio_id
                    == LotDisposalReceiptRecord.portfolio_id,
                    LotDisposalAllocationRecord.security_id == LotDisposalReceiptRecord.security_id,
                ),
            )
            .where(
                LotDisposalReceiptRecord.portfolio_id == portfolio_id,
                LotDisposalReceiptRecord.disposal_transaction_id == transaction_id,
                LotDisposalReceiptRecord.receipt_version == latest_version,
            )
            .order_by(LotDisposalAllocationRecord.allocation_ordinal.asc())
        )
        rows = (await self.db.execute(statement)).all()
        if not rows:
            return None
        receipt = rows[0][0]
        allocations = [allocation for _, allocation in rows if allocation is not None]
        return receipt, allocations
