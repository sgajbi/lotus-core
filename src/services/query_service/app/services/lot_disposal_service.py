"""Serve immutable lot-consumption supportability across transaction families."""

from portfolio_common.domain.tenant import TenantContext
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.lot_disposal_dto import (
    LotDisposalAllocationResponse,
    LotDisposalReceiptResponse,
)
from ..repositories.lot_disposal_repository import LotDisposalRepository
from .portfolio_validation import ensure_portfolio_owned


class LotDisposalService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = LotDisposalRepository(db)

    async def get_latest_receipt(
        self,
        *,
        tenant_context: TenantContext,
        portfolio_id: str,
        transaction_id: str,
    ) -> LotDisposalReceiptResponse:
        await ensure_portfolio_owned(
            repository=self.repo,
            tenant_id=tenant_context.tenant_id_text,
            portfolio_id=portfolio_id,
        )
        result = await self.repo.get_latest_receipt(
            portfolio_id=portfolio_id,
            transaction_id=transaction_id,
        )
        if result is None:
            raise LookupError(
                f"Lot-disposal receipt not found for portfolio {portfolio_id} and "
                f"transaction {transaction_id}"
            )
        receipt, allocations = result
        return LotDisposalReceiptResponse(
            receipt_id=receipt.receipt_id,
            receipt_version=receipt.receipt_version,
            disposal_transaction_id=receipt.disposal_transaction_id,
            portfolio_id=receipt.portfolio_id,
            instrument_id=receipt.instrument_id,
            security_id=receipt.security_id,
            disposal_timestamp=receipt.disposal_timestamp,
            transaction_type=receipt.transaction_type,
            destination_type=receipt.destination_type,
            target_transaction_id=receipt.target_transaction_id,
            target_lot_id=receipt.target_lot_id,
            target_instrument_id=receipt.target_instrument_id,
            external_destination_reference=receipt.external_destination_reference,
            cost_basis_method=receipt.cost_basis_method,
            calculation_policy_id=receipt.calculation_policy_id,
            calculation_policy_version=receipt.calculation_policy_version,
            status=receipt.status,
            void_reason=receipt.void_reason,
            consumed_quantity=receipt.consumed_quantity,
            consumed_cost_local=receipt.consumed_cost_local,
            consumed_cost_base=receipt.consumed_cost_base,
            semantic_content_hash=receipt.semantic_content_hash,
            previous_receipt_content_hash=receipt.previous_receipt_content_hash,
            receipt_content_hash=receipt.receipt_content_hash,
            transaction_calculation_lineage=receipt.transaction_calculation_lineage,
            disposal_calculation_lineage=receipt.disposal_calculation_lineage,
            allocations=[
                LotDisposalAllocationResponse(
                    allocation_ordinal=allocation.allocation_ordinal,
                    source_lot_id=allocation.source_lot_id,
                    source_transaction_id=allocation.source_transaction_id,
                    source_acquisition_date=allocation.source_acquisition_date,
                    consumed_quantity=allocation.consumed_quantity,
                    consumed_cost_local=allocation.consumed_cost_local,
                    consumed_cost_base=allocation.consumed_cost_base,
                    allocation_content_hash=allocation.allocation_content_hash,
                    amortized_cost_profile_id=allocation.amortized_cost_profile_id,
                    amortized_cost_profile_version=allocation.amortized_cost_profile_version,
                    amortized_cost_profile_content_hash=(
                        allocation.amortized_cost_profile_content_hash
                    ),
                    amortized_cost_currency=allocation.amortized_cost_currency,
                    amortized_cost_recognized_through=(
                        allocation.amortized_cost_recognized_through
                    ),
                    amortized_cost_original_quantity=(allocation.amortized_cost_original_quantity),
                    amortized_cost_open_quantity_before=(
                        allocation.amortized_cost_open_quantity_before
                    ),
                    amortized_cost_residual_quantity=(allocation.amortized_cost_residual_quantity),
                    amortized_cost_scheduled_local=allocation.amortized_cost_scheduled_local,
                    amortized_cost_current_local=allocation.amortized_cost_current_local,
                    amortized_cost_current_base=allocation.amortized_cost_current_base,
                    amortized_cost_residual_local=allocation.amortized_cost_residual_local,
                    amortized_cost_book_fx_rate_to_base=(
                        allocation.amortized_cost_book_fx_rate_to_base
                    ),
                    amortized_cost_residual_base=allocation.amortized_cost_residual_base,
                    amortized_cost_retained_rounding_local=(
                        allocation.amortized_cost_retained_rounding_local
                    ),
                    amortized_cost_retained_rounding_base=(
                        allocation.amortized_cost_retained_rounding_base
                    ),
                    amortized_cost_calculation_lineage=(
                        allocation.amortized_cost_calculation_lineage
                    ),
                )
                for allocation in allocations
            ],
        )
