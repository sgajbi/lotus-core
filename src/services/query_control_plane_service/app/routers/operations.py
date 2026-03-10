import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.operations_dto import (
    CalculatorSloResponse,
    LineageKeyListResponse,
    LineageResponse,
    SupportJobListResponse,
    SupportOverviewResponse,
)
from src.services.query_service.app.services.operations_service import OperationsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operations Support"])


def get_operations_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> OperationsService:
    return OperationsService(db)


@router.get(
    "/support/portfolios/{portfolio_id}/overview",
    response_model=SupportOverviewResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="Get operational support overview for a portfolio",
    description=(
        "What: Return support-oriented operational state for one portfolio.\n"
        "How: Aggregate reprocessing, valuation, and latest-data availability markers "
        "for the key.\n"
        "When: Use during incidents to quickly assess whether portfolio processing is healthy."
    ),
)
async def get_support_overview(
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_support_overview(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to build support overview for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building support overview.",
        )


@router.get(
    "/support/portfolios/{portfolio_id}/calculator-slos",
    response_model=CalculatorSloResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="Get calculator SLO baseline snapshot for a portfolio",
    description=(
        "What: Return calculator backlog, stale-processing, and failed-job baselines for one "
        "portfolio.\n"
        "How: Aggregate valuation/aggregation job states and reprocessing key counts in a single "
        "support payload.\n"
        "When: Use before scaling actions, during incidents, and for daily operational SLO checks."
    ),
)
async def get_calculator_slos(
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    stale_threshold_minutes: int = Query(
        15,
        ge=1,
        le=1440,
        description="Threshold in minutes used to classify stale PROCESSING jobs.",
    ),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_calculator_slos(
            portfolio_id=portfolio_id, stale_threshold_minutes=stale_threshold_minutes
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to build calculator SLO snapshot for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building calculator SLO snapshot.",
        )


@router.get(
    "/support/portfolios/{portfolio_id}/valuation-jobs",
    response_model=SupportJobListResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="List valuation jobs for support workflows",
    description=(
        "What: List valuation jobs for a portfolio with support filters.\n"
        "How: Query valuation job records with pagination and optional status filtering.\n"
        "When: Use to triage stuck valuation workloads and verify drain progress."
    ),
)
async def get_valuation_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    status_filter: Optional[str] = Query(
        None, description="Optional job status filter (e.g., PENDING, PROCESSING)."
    ),
    skip: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_valuation_jobs(
            portfolio_id=portfolio_id, skip=skip, limit=limit, status=status_filter
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list valuation jobs for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing valuation jobs.",
        )


@router.get(
    "/support/portfolios/{portfolio_id}/aggregation-jobs",
    response_model=SupportJobListResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="List aggregation jobs for support workflows",
    description=(
        "What: List portfolio aggregation jobs for support workflows.\n"
        "How: Query aggregation job records with pagination and optional status filtering.\n"
        "When: Use when portfolio rollups are stale or downstream timeseries appears delayed."
    ),
)
async def get_aggregation_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    status_filter: Optional[str] = Query(
        None, description="Optional job status filter (e.g., PENDING, PROCESSING)."
    ),
    skip: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_aggregation_jobs(
            portfolio_id=portfolio_id, skip=skip, limit=limit, status=status_filter
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list aggregation jobs for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing aggregation jobs.",
        )


@router.get(
    "/lineage/portfolios/{portfolio_id}/securities/{security_id}",
    response_model=LineageResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio/security lineage not found."}},
    summary="Get lineage state for a portfolio-security key",
    description=(
        "What: Return lineage state for one portfolio-security key.\n"
        "How: Read epoch, watermark, and latest artifact pointers from lineage state services.\n"
        "When: Use during replay/reprocessing investigations for deterministic state validation."
    ),
)
async def get_lineage(
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    security_id: str = Path(..., description="Security identifier."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_lineage(portfolio_id, security_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception(
            "Failed to build lineage for portfolio %s security %s", portfolio_id, security_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building lineage response.",
        )


@router.get(
    "/lineage/portfolios/{portfolio_id}/keys",
    response_model=LineageKeyListResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="List lineage keys for a portfolio",
    description=(
        "What: List lineage keys for a portfolio.\n"
        "How: Query portfolio-security lineage rows with status/security filters and pagination.\n"
        "When: Use to scope impacted keys before running replay, backfill, or targeted recovery."
    ),
)
async def get_lineage_keys(
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    reprocessing_status: Optional[str] = Query(
        None, description="Optional status filter for lineage keys (e.g., CURRENT, REPROCESSING)."
    ),
    security_id: Optional[str] = Query(
        None, description="Optional security filter to narrow lineage key results."
    ),
    skip: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_lineage_keys(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            reprocessing_status=reprocessing_status,
            security_id=security_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list lineage keys for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing lineage keys.",
        )
