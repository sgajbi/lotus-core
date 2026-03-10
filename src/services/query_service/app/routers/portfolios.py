# services/query-service/app/routers/portfolios.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.portfolio_dto import PortfolioQueryResponse, PortfolioRecord
from ..services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["Portfolios"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {
    "detail": "Portfolio with id PORT-DISC-001 not found"
}


def get_portfolio_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioService:
    return PortfolioService(db)


@router.get(
    "/",
    response_model=PortfolioQueryResponse,
    summary="Get Portfolio Details",
    description=(
        "Returns portfolios with optional filtering by portfolio ID, CIF, and booking center. "
        "Used by UI/lotus-gateway for portfolio discovery and navigation."
    ),
)
async def get_portfolios(
    portfolio_id: Optional[str] = Query(
        None,
        description="Filter by a single, specific portfolio ID.",
        examples=["PORT-DISC-001"],
    ),
    client_id: Optional[str] = Query(
        None,
        description="Filter by the client grouping ID (CIF) to get all portfolios for a client.",
        examples=["CIF-100200"],
    ),
    booking_center_code: Optional[str] = Query(
        None,
        description="Filter by booking center to get all portfolios for a business unit.",
        examples=["SGPB"],
    ),
    service: PortfolioService = Depends(get_portfolio_service),
):
    try:
        return await service.get_portfolios(
            portfolio_id=portfolio_id, client_id=client_id, booking_center_code=booking_center_code
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}",
        )


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioRecord,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get a Single Portfolio by ID",
    description="Returns the canonical portfolio record for a single portfolio identifier.",
)
async def get_portfolio_by_id(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-DISC-001"],
    ),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """
    Retrieves a single portfolio by its unique ID.
    Returns a `404 Not Found` if the portfolio does not exist.
    """
    try:
        portfolio = await service.get_portfolio_by_id(portfolio_id)
        return portfolio
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio with id {portfolio_id} not found",
        )
