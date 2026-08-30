"""Serve source-to-target basis-transfer lineage without disposal aliases."""

from portfolio_common.domain.tenant import TenantContext
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.lot_basis_transfer_dto import (
    LotBasisTransferAllocationResponse,
    LotBasisTransferReceiptResponse,
)
from ..repositories.lot_basis_transfer_repository import LotBasisTransferRepository
from .portfolio_validation import ensure_portfolio_owned


class LotBasisTransferService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = LotBasisTransferRepository(db)

    async def get_latest_receipt(
        self,
        *,
        tenant_context: TenantContext,
        portfolio_id: str,
        source_transaction_id: str,
    ) -> LotBasisTransferReceiptResponse:
        await ensure_portfolio_owned(
            repository=self.repo,
            tenant_id=tenant_context.tenant_id_text,
            portfolio_id=portfolio_id,
        )
        result = await self.repo.get_latest_receipt(
            portfolio_id=portfolio_id,
            source_transaction_id=source_transaction_id,
        )
        if result is None:
            raise LookupError(
                f"Lot basis-transfer receipt not found for portfolio {portfolio_id} and "
                f"source transaction {source_transaction_id}"
            )
        receipt, allocations = result
        return LotBasisTransferReceiptResponse(
            **{
                field_name: getattr(receipt, field_name)
                for field_name in LotBasisTransferReceiptResponse.model_fields
                if field_name != "allocations"
            },
            allocations=[
                LotBasisTransferAllocationResponse.model_validate(item, from_attributes=True)
                for item in allocations
            ],
        )
