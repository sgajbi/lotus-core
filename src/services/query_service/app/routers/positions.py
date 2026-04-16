# services/query-service/app/routers/positions.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from portfolio_common.source_data_products import source_data_product_openapi_extra
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.position_dto import PortfolioPositionHistoryResponse, PortfolioPositionsResponse
from ..services.position_service import PositionService

router = APIRouter(prefix="/portfolios", tags=["Positions"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-POS-001 not found"}


def get_position_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PositionService:
    return PositionService(db)


@router.get(
    "/{portfolio_id}/position-history",
    response_model=PortfolioPositionHistoryResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get Position History for a Security",
    description=(
        "Returns epoch-aware position history for a portfolio-security key across a date range. "
        "Used for drill-down views and lineage-aware troubleshooting."
    ),
)
async def get_position_history(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-POS-001"],
    ),
    security_id: str = Query(
        ...,
        description="Security identifier for the position-history drill-down.",
        examples=["SEC-US-AAPL"],
    ),
    start_date: Optional[date] = Query(
        None,
        description="The start date for the date range filter (inclusive).",
        examples=["2026-01-01"],
    ),
    end_date: Optional[date] = Query(
        None,
        description="The end date for the date range filter (inclusive).",
        examples=["2026-03-31"],
    ),
    service: PositionService = Depends(get_position_service),
):
    try:
        return await service.get_position_history(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {exc}",
        )


@router.get(
    "/{portfolio_id}/positions",
    response_model=PortfolioPositionsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get Latest Positions for a Portfolio",
    description=(
        "What: Return the strategic HoldingsAsOf operational read for one portfolio.\n"
        "How: Resolves current-epoch holdings from daily position snapshots, supplements gaps from "
        "position history when snapshot materialization has not caught up yet, and publishes "
        "source-data runtime metadata with holdings-level data-quality posture.\n"
        "When: Use this route for holdings screens, gateway portfolio position books, and other "
        "downstream consumers that need the governed source-of-truth holdings surface. Use "
        "`as_of_date` for booked historical state on or before a specific business date. Use "
        "`include_projected=true` only when the consumer intentionally wants future-dated "
        "projected state beyond the latest booked business date. Do not treat this route as a "
        "substitute for performance, risk, or reporting-specific aggregation contracts, and do "
        "not prefer deprecated reporting convenience shapes when this operational read meets the "
        "consumer need."
    ),
    openapi_extra=source_data_product_openapi_extra("HoldingsAsOf"),
)
async def get_latest_positions(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-POS-001"],
    ),
    as_of_date: Optional[date] = Query(
        None,
        description=(
            "Optional as-of date for booked position state. When omitted and "
            "`include_projected=false`, lotus-core resolves the latest booked business date."
        ),
        examples=["2026-03-10"],
    ),
    include_projected: bool = Query(
        False,
        description=(
            "When true, returns the latest projected state even if future-dated transactions push "
            "holdings beyond the latest booked business_date."
        ),
        examples=[False],
    ),
    service: PositionService = Depends(get_position_service),
):
    try:
        return await service.get_portfolio_positions(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            include_projected=include_projected,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {exc}",
        )
