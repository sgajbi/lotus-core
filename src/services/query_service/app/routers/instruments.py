from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import pagination_params
from ..dtos.instrument_dto import PaginatedInstrumentResponse
from ..services.instrument_service import InstrumentService

router = APIRouter(prefix="/instruments", tags=["Instruments"])


@router.get(
    "/",
    response_model=PaginatedInstrumentResponse,
    summary="Get a List of Instruments",
    description=(
        "Returns reference instrument records with optional filtering by security and product "
        "type. "
        "Used by lookup selectors and enrichment workflows."
    ),
)
async def get_instruments(
    security_id: Optional[str] = Query(
        None,
        description="Filter by a specific security identifier.",
        examples=["SEC-US-AAPL"],
    ),
    product_type: Optional[str] = Query(
        None,
        description="Filter by a specific product type such as Equity or Bond.",
        examples=["Equity"],
    ),
    pagination: Dict[str, int] = Depends(pagination_params),
    db: AsyncSession = Depends(get_async_db_session),
):
    service = InstrumentService(db)
    return await service.get_instruments(
        security_id=security_id, product_type=product_type, **pagination
    )
