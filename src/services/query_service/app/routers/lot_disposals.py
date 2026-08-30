"""Transaction-neutral lot-disposal supportability routes."""

from fastapi import APIRouter, Depends, Path, Request, status

from ..dependencies import get_lot_disposal_service
from ..dtos.lot_disposal_dto import LotDisposalReceiptResponse
from ..services.lot_disposal_service import LotDisposalService
from .http_errors import lookup_error_to_http

router = APIRouter(prefix="/portfolios", tags=["Lot Disposal Receipts"])


@router.get(
    "/{portfolio_id}/transactions/{transaction_id}/lot-disposal-receipt",
    response_model=LotDisposalReceiptResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio or lot-disposal receipt not found.",
        }
    },
    summary="Get Latest Immutable Lot-Disposal Receipt",
    description=(
        "Returns the latest versioned receipt and ordered source-lot allocations for any "
        "governed lot-consuming transaction family, including SELL and fixed-income redemption."
    ),
)
async def get_latest_lot_disposal_receipt(
    request: Request,
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    transaction_id: str = Path(..., description="Lot-consuming transaction identifier."),
    service: LotDisposalService = Depends(get_lot_disposal_service),
) -> LotDisposalReceiptResponse:
    try:
        receipt: LotDisposalReceiptResponse = await service.get_latest_receipt(
            tenant_context=request.state.tenant_context,
            portfolio_id=portfolio_id,
            transaction_id=transaction_id,
        )
        return receipt
    except LookupError as exc:
        raise lookup_error_to_http(exc) from exc
