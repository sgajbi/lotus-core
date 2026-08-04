"""Read immutable lot-disposal receipts without transaction-family assumptions."""

from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    Portfolio,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .lot_disposal_records import (
    LotDisposalAllocationReadRecord,
    LotDisposalReceiptReadRecord,
)


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
    ) -> tuple[LotDisposalReceiptReadRecord, list[LotDisposalAllocationReadRecord]] | None:
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
        receipt = _receipt_record(rows[0][0])
        allocations = [
            _allocation_record(allocation) for _, allocation in rows if allocation is not None
        ]
        return receipt, allocations


def _receipt_record(record: LotDisposalReceiptRecord) -> LotDisposalReceiptReadRecord:
    return LotDisposalReceiptReadRecord(
        receipt_id=record.receipt_id,
        receipt_version=record.receipt_version,
        disposal_transaction_id=record.disposal_transaction_id,
        portfolio_id=record.portfolio_id,
        instrument_id=record.instrument_id,
        security_id=record.security_id,
        disposal_timestamp=record.disposal_timestamp,
        transaction_type=record.transaction_type,
        destination_type=record.destination_type,
        target_transaction_id=record.target_transaction_id,
        target_lot_id=record.target_lot_id,
        target_instrument_id=record.target_instrument_id,
        external_destination_reference=record.external_destination_reference,
        cost_basis_method=record.cost_basis_method,
        calculation_policy_id=record.calculation_policy_id,
        calculation_policy_version=record.calculation_policy_version,
        status=record.status,
        void_reason=record.void_reason,
        consumed_quantity=record.consumed_quantity,
        consumed_cost_local=record.consumed_cost_local,
        consumed_cost_base=record.consumed_cost_base,
        semantic_content_hash=record.semantic_content_hash,
        previous_receipt_content_hash=record.previous_receipt_content_hash,
        receipt_content_hash=record.receipt_content_hash,
        transaction_calculation_lineage=record.transaction_calculation_lineage,
        disposal_calculation_lineage=record.disposal_calculation_lineage,
    )


def _allocation_record(
    record: LotDisposalAllocationRecord,
) -> LotDisposalAllocationReadRecord:
    return LotDisposalAllocationReadRecord(
        allocation_ordinal=record.allocation_ordinal,
        source_lot_id=record.source_lot_id,
        source_transaction_id=record.source_transaction_id,
        source_acquisition_date=record.source_acquisition_date,
        consumed_quantity=record.consumed_quantity,
        consumed_cost_local=record.consumed_cost_local,
        consumed_cost_base=record.consumed_cost_base,
        allocation_content_hash=record.allocation_content_hash,
        amortized_cost_profile_id=record.amortized_cost_profile_id,
        amortized_cost_profile_version=record.amortized_cost_profile_version,
        amortized_cost_profile_content_hash=record.amortized_cost_profile_content_hash,
        amortized_cost_recognized_through=record.amortized_cost_recognized_through,
        amortized_cost_calculation_lineage=record.amortized_cost_calculation_lineage,
    )
