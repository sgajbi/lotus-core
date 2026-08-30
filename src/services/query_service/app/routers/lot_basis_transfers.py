"""Source-to-target lot basis-transfer supportability routes."""

from fastapi import APIRouter, Depends, Path, Request, status

from ..dependencies import get_lot_basis_transfer_service
from ..dtos.lot_basis_transfer_dto import LotBasisTransferReceiptResponse
from ..services.lot_basis_transfer_service import LotBasisTransferService
from .http_errors import lookup_error_to_http

router = APIRouter(prefix="/portfolios", tags=["Lot Basis-Transfer Receipts"])


@router.get(
    "/{portfolio_id}/transactions/{source_transaction_id}/lot-basis-transfer-receipt",
    response_model=LotBasisTransferReceiptResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio or lot basis-transfer receipt not found.",
        }
    },
    summary="Get Latest Immutable Lot Basis-Transfer Receipt",
    description=(
        "Returns the latest versioned source-to-target lot lineage and ordered source-lot "
        "basis allocations for a governed basis-only corporate action."
    ),
)
async def get_latest_lot_basis_transfer_receipt(
    request: Request,
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    source_transaction_id: str = Path(
        ..., description="Source transaction that transferred lot basis."
    ),
    service: LotBasisTransferService = Depends(get_lot_basis_transfer_service),
) -> LotBasisTransferReceiptResponse:
    try:
        receipt: LotBasisTransferReceiptResponse = await service.get_latest_receipt(
            tenant_context=request.state.tenant_context,
            portfolio_id=portfolio_id,
            source_transaction_id=source_transaction_id,
        )
        return receipt
    except LookupError as exc:
        raise lookup_error_to_http(exc) from exc
