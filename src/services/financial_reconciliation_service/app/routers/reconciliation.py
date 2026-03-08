from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos import (
    ReconciliationFindingListResponse,
    ReconciliationRunListResponse,
    ReconciliationRunRequest,
    ReconciliationRunResponse,
)
from ..repositories import ReconciliationRepository
from ..services import ReconciliationService

router = APIRouter(tags=["financial-reconciliation"])


def _service(db_session: AsyncSession) -> ReconciliationService:
    return ReconciliationService(ReconciliationRepository(db_session))


@router.post(
    "/reconciliation/runs/transaction-cashflow",
    response_model=ReconciliationRunResponse,
    summary="Run transaction-to-cashflow completeness controls",
    description=(
        "What: Execute an independent control that validates every transaction with a "
        "cashflow rule has exactly one aligned cashflow row.\n"
        "How: Compare transactions, cashflow_rules, and cashflows for the requested "
        "scope.\n"
        "Why: Prevent silent ledger-to-cashflow drift before downstream analytics "
        "consume corrupted flows."
    ),
)
async def run_transaction_cashflow_reconciliation(
    request: ReconciliationRunRequest,
    db_session: AsyncSession = Depends(get_async_db_session),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
):
    service = _service(db_session)
    run = await service.run_transaction_cashflow(request=request, correlation_id=x_correlation_id)
    await db_session.commit()
    return run


@router.post(
    "/reconciliation/runs/position-valuation",
    response_model=ReconciliationRunResponse,
    summary="Run position-to-valuation consistency controls",
    description=(
        "What: Validate valued daily snapshots against core arithmetic invariants.\n"
        "How: Recompute market value and unrealized gain/loss from stored quantity, "
        "price, and cost basis.\n"
        "Why: Detect valuation drift without relying on calculator-internal assumptions."
    ),
)
async def run_position_valuation_reconciliation(
    request: ReconciliationRunRequest,
    db_session: AsyncSession = Depends(get_async_db_session),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
):
    service = _service(db_session)
    run = await service.run_position_valuation(request=request, correlation_id=x_correlation_id)
    await db_session.commit()
    return run


@router.post(
    "/reconciliation/runs/timeseries-integrity",
    response_model=ReconciliationRunResponse,
    summary="Run portfolio timeseries integrity controls",
    description=(
        "What: Validate portfolio timeseries rows against aggregated position "
        "timeseries and input completeness.\n"
        "How: Re-aggregate position timeseries and compare against portfolio rows "
        "and snapshot counts.\n"
        "Why: Catch partial aggregation or drift before consumers treat portfolio "
        "analytics as authoritative."
    ),
)
async def run_timeseries_integrity_reconciliation(
    request: ReconciliationRunRequest,
    db_session: AsyncSession = Depends(get_async_db_session),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
):
    service = _service(db_session)
    run = await service.run_timeseries_integrity(request=request, correlation_id=x_correlation_id)
    await db_session.commit()
    return run


@router.get(
    "/reconciliation/runs",
    response_model=ReconciliationRunListResponse,
    summary="List reconciliation control runs",
)
async def list_reconciliation_runs(
    reconciliation_type: str | None = Query(default=None),
    portfolio_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db_session: AsyncSession = Depends(get_async_db_session),
):
    repository = ReconciliationRepository(db_session)
    runs = await repository.list_runs(
        reconciliation_type=reconciliation_type,
        portfolio_id=portfolio_id,
        limit=limit,
    )
    return ReconciliationRunListResponse(runs=runs, total=len(runs))


@router.get(
    "/reconciliation/runs/{run_id}",
    response_model=ReconciliationRunResponse,
    summary="Get one reconciliation control run",
)
async def get_reconciliation_run(
    run_id: str,
    db_session: AsyncSession = Depends(get_async_db_session),
):
    repository = ReconciliationRepository(db_session)
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=f"Reconciliation run '{run_id}' was not found.",
        )
    return run


@router.get(
    "/reconciliation/runs/{run_id}/findings",
    response_model=ReconciliationFindingListResponse,
    summary="List findings for one reconciliation control run",
)
async def list_reconciliation_findings(
    run_id: str,
    db_session: AsyncSession = Depends(get_async_db_session),
):
    repository = ReconciliationRepository(db_session)
    findings = await repository.list_findings(run_id)
    return ReconciliationFindingListResponse(findings=findings, total=len(findings))
