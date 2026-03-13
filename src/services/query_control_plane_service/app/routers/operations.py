import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.operations_dto import (
    AnalyticsExportJobListResponse,
    CalculatorSloResponse,
    LineageKeyListResponse,
    LineageResponse,
    ReconciliationFindingListResponse,
    ReconciliationRunListResponse,
    SupportJobListResponse,
    SupportOverviewResponse,
)
from src.services.query_service.app.services.operations_service import OperationsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operations Support"])

PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE = {"detail": "Portfolio with id PORT-OPS-001 not found"}

LINEAGE_NOT_FOUND_RESPONSE_EXAMPLE = {
    "detail": "Lineage for portfolio PORT-OPS-001 and security SEC-US-IBM not found"
}


def get_operations_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> OperationsService:
    return OperationsService(db)


@router.get(
    "/support/portfolios/{portfolio_id}/overview",
    response_model=SupportOverviewResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get operational support overview for a portfolio",
    description=(
        "What: Return support-oriented operational state for one portfolio.\n"
        "How: Aggregate reprocessing, valuation, and latest-data availability markers "
        "for the key.\n"
        "When: Use during incidents to quickly assess whether portfolio processing is healthy."
    ),
)
async def get_support_overview(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-OPS-001"],
    ),
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
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
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
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier.",
        examples=["PORT-OPS-001"],
    ),
    stale_threshold_minutes: int = Query(
        15,
        ge=1,
        le=1440,
        description="Threshold in minutes used to classify stale PROCESSING jobs.",
        examples=[15],
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
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="List valuation jobs for support workflows",
    description=(
        "What: List valuation jobs for a portfolio with support filters.\n"
        "How: Query valuation job records with pagination and optional status filtering.\n"
        "When: Use to triage stuck valuation workloads and verify drain progress."
    ),
)
async def get_valuation_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    status_filter: Optional[str] = Query(
        None,
        description="Optional job status filter (e.g., PENDING, PROCESSING).",
        examples=["PENDING"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
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
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="List aggregation jobs for support workflows",
    description=(
        "What: List portfolio aggregation jobs for support workflows.\n"
        "How: Query aggregation job records with pagination and optional status filtering.\n"
        "When: Use when portfolio rollups are stale or downstream timeseries appears delayed."
    ),
)
async def get_aggregation_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    status_filter: Optional[str] = Query(
        None,
        description="Optional job status filter (e.g., PENDING, PROCESSING).",
        examples=["PENDING"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
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
    "/support/portfolios/{portfolio_id}/analytics-export-jobs",
    response_model=AnalyticsExportJobListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="List analytics export jobs for support workflows",
    description=(
        "What: List durable analytics export jobs for a portfolio with support filters.\n"
        "How: Query export job lifecycle records with pagination and optional status filtering.\n"
        "When: Use to investigate stuck, failed, or repeated analytics export requests."
    ),
)
async def get_analytics_export_jobs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    status_filter: Optional[str] = Query(
        None,
        description="Optional export job status filter (e.g., accepted, running, failed).",
        examples=["failed"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_analytics_export_jobs(
            portfolio_id=portfolio_id, skip=skip, limit=limit, status=status_filter
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list analytics export jobs for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing analytics export jobs.",
        )


@router.get(
    "/support/portfolios/{portfolio_id}/reconciliation-runs",
    response_model=ReconciliationRunListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="List reconciliation runs for support workflows",
    description=(
        "What: List durable reconciliation control runs for a portfolio.\n"
        "How: Query reconciliation run records with pagination and optional type/status filters.\n"
        "When: Use to investigate blocked portfolio-day controls, repeated replay demands, or "
        "unexpected reconciliation failures."
    ),
)
async def get_reconciliation_runs(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    reconciliation_type: Optional[str] = Query(
        None,
        description="Optional reconciliation type filter (e.g., transaction_cashflow).",
        examples=["transaction_cashflow"],
    ),
    status_filter: Optional[str] = Query(
        None,
        description="Optional run status filter (e.g., COMPLETED, FAILED, REQUIRES_REPLAY).",
        examples=["FAILED"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_reconciliation_runs(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            reconciliation_type=reconciliation_type,
            status=status_filter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list reconciliation runs for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing reconciliation runs.",
        )


@router.get(
    "/support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings",
    response_model=ReconciliationFindingListResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio or reconciliation run not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="List reconciliation findings for one support run",
    description=(
        "What: Return durable findings for one reconciliation run.\n"
        "How: Query persisted reconciliation findings scoped to the requested run identifier.\n"
        "When: Use after a control failure or replay requirement to inspect the exact breaches "
        "that blocked publication."
    ),
)
async def get_reconciliation_findings(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    run_id: str = Path(
        ...,
        description="Reconciliation run identifier.",
        examples=["recon_1234567890abcdef"],
    ),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum findings to return.", examples=[100]
    ),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_reconciliation_findings(
            portfolio_id=portfolio_id,
            run_id=run_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception(
            "Failed to list reconciliation findings for portfolio %s run %s",
            portfolio_id,
            run_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing reconciliation findings.",
        )


@router.get(
    "/lineage/portfolios/{portfolio_id}/securities/{security_id}",
    response_model=LineageResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio/security lineage not found.",
            "content": {"application/json": {"example": LINEAGE_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="Get lineage state for a portfolio-security key",
    description=(
        "What: Return lineage state for one portfolio-security key.\n"
        "How: Read epoch, watermark, and latest artifact pointers from lineage state services.\n"
        "When: Use during replay/reprocessing investigations for deterministic state validation."
    ),
)
async def get_lineage(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    security_id: str = Path(..., description="Security identifier.", examples=["SEC-US-IBM"]),
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
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_NOT_FOUND_RESPONSE_EXAMPLE}},
        }
    },
    summary="List lineage keys for a portfolio",
    description=(
        "What: List lineage keys for a portfolio.\n"
        "How: Query portfolio-security lineage rows with status/security filters and pagination.\n"
        "When: Use to scope impacted keys before running replay, backfill, or targeted recovery."
    ),
)
async def get_lineage_keys(
    portfolio_id: str = Path(..., description="Portfolio identifier.", examples=["PORT-OPS-001"]),
    reprocessing_status: Optional[str] = Query(
        None,
        description="Optional status filter for lineage keys (e.g., CURRENT, REPROCESSING).",
        examples=["CURRENT"],
    ),
    security_id: Optional[str] = Query(
        None,
        description="Optional security filter to narrow lineage key results.",
        examples=["SEC-US-IBM"],
    ),
    skip: int = Query(0, ge=0, description="Pagination offset.", examples=[0]),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit.", examples=[100]),
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
