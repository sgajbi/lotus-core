from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Query
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

NOT_FOUND_RESPONSE_EXAMPLE = {
    "detail": "Reconciliation run 'FRR-20260306-0001' was not found."
}

RECONCILIATION_RUN_REQUEST_EXAMPLES = {
    "portfolio_day_scope": {
        "summary": "Portfolio-day scoped control run",
        "description": (
            "Run a deterministic control for one portfolio, one business date, and one epoch."
        ),
        "value": {
            "portfolio_id": "PORT-OPS-001",
            "business_date": "2026-03-06",
            "epoch": 0,
            "requested_by": "ops_control_plane",
            "tolerance": "0.01",
        },
    },
    "all_portfolios_day_scope": {
        "summary": "Estate-wide day scan",
        "description": "Run the control across all portfolios for one business date.",
        "value": {
            "business_date": "2026-03-06",
            "requested_by": "daily_control_scheduler",
            "tolerance": "0.05",
        },
    },
}

RECONCILIATION_RUN_RESPONSE_EXAMPLE = {
    "run_id": "FRR-20260306-0001",
    "reconciliation_type": "transaction_cashflow",
    "portfolio_id": "PORT-OPS-001",
    "business_date": "2026-03-06",
    "epoch": 0,
    "status": "completed",
    "requested_by": "ops_control_plane",
    "correlation_id": "CTL:9b4db9d1-1a39-42f2-9f55-2b2a4f9a4700",
    "tolerance": "0.01",
    "summary": {"checked_transactions": 142, "finding_count": 1, "passed": False},
    "failure_reason": None,
    "started_at": "2026-03-06T14:03:10Z",
    "completed_at": "2026-03-06T14:03:11Z",
    "created_at": "2026-03-06T14:03:10Z",
    "updated_at": "2026-03-06T14:03:11Z",
}

RECONCILIATION_FINDING_LIST_RESPONSE_EXAMPLE = {
    "findings": [
        {
            "finding_id": "FRF-20260306-0001",
            "run_id": "FRR-20260306-0001",
            "reconciliation_type": "transaction_cashflow",
            "finding_type": "missing_cashflow",
            "severity": "high",
            "portfolio_id": "PORT-OPS-001",
            "security_id": "SEC-US-IBM",
            "transaction_id": "TXN-20260306-0142",
            "business_date": "2026-03-06",
            "epoch": 0,
            "expected_value": {"cashflow_count": 1},
            "observed_value": {"cashflow_count": 0},
            "detail": {
                "rule_transaction_type": "BUY",
                "reason": "Transaction has a cashflow rule but no persisted cashflow row.",
            },
            "created_at": "2026-03-06T14:03:11Z",
        }
    ],
    "total": 1,
}


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
    responses={
        200: {
            "description": "Completed reconciliation run.",
            "content": {"application/json": {"example": RECONCILIATION_RUN_RESPONSE_EXAMPLE}},
        }
    },
)
async def run_transaction_cashflow_reconciliation(
    request: ReconciliationRunRequest = Body(openapi_examples=RECONCILIATION_RUN_REQUEST_EXAMPLES),
    db_session: AsyncSession = Depends(get_async_db_session),
    x_correlation_id: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
        description="Optional correlation identifier propagated into the recorded reconciliation run.",
        examples=["CTL:9b4db9d1-1a39-42f2-9f55-2b2a4f9a4700"],
    ),
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
    responses={
        200: {
            "description": "Completed reconciliation run.",
            "content": {"application/json": {"example": RECONCILIATION_RUN_RESPONSE_EXAMPLE}},
        }
    },
)
async def run_position_valuation_reconciliation(
    request: ReconciliationRunRequest = Body(openapi_examples=RECONCILIATION_RUN_REQUEST_EXAMPLES),
    db_session: AsyncSession = Depends(get_async_db_session),
    x_correlation_id: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
        description="Optional correlation identifier propagated into the recorded reconciliation run.",
        examples=["CTL:9b4db9d1-1a39-42f2-9f55-2b2a4f9a4700"],
    ),
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
    responses={
        200: {
            "description": "Completed reconciliation run.",
            "content": {"application/json": {"example": RECONCILIATION_RUN_RESPONSE_EXAMPLE}},
        }
    },
)
async def run_timeseries_integrity_reconciliation(
    request: ReconciliationRunRequest = Body(openapi_examples=RECONCILIATION_RUN_REQUEST_EXAMPLES),
    db_session: AsyncSession = Depends(get_async_db_session),
    x_correlation_id: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
        description="Optional correlation identifier propagated into the recorded reconciliation run.",
        examples=["CTL:9b4db9d1-1a39-42f2-9f55-2b2a4f9a4700"],
    ),
):
    service = _service(db_session)
    run = await service.run_timeseries_integrity(request=request, correlation_id=x_correlation_id)
    await db_session.commit()
    return run


@router.get(
    "/reconciliation/runs",
    response_model=ReconciliationRunListResponse,
    summary="List reconciliation control runs",
    responses={
        200: {
            "description": "Reconciliation runs matching the requested filters.",
            "content": {
                "application/json": {
                    "example": {
                        "runs": [RECONCILIATION_RUN_RESPONSE_EXAMPLE],
                        "total": 1,
                    }
                }
            },
        }
    },
)
async def list_reconciliation_runs(
    reconciliation_type: str | None = Query(
        default=None,
        description="Optional reconciliation type filter.",
        examples=["transaction_cashflow"],
    ),
    portfolio_id: str | None = Query(
        default=None,
        description="Optional portfolio filter.",
        examples=["PORT-OPS-001"],
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of runs to return.",
        examples=[50],
    ),
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
    responses={
        200: {
            "description": "One reconciliation run.",
            "content": {"application/json": {"example": RECONCILIATION_RUN_RESPONSE_EXAMPLE}},
        },
        404: {
            "description": "Run was not found.",
            "content": {"application/json": {"example": NOT_FOUND_RESPONSE_EXAMPLE}},
        },
    },
)
async def get_reconciliation_run(
    run_id: str = Path(
        description="Reconciliation run identifier.",
        examples=["FRR-20260306-0001"],
    ),
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
    responses={
        200: {
            "description": "Findings captured for the requested reconciliation run.",
            "content": {
                "application/json": {"example": RECONCILIATION_FINDING_LIST_RESPONSE_EXAMPLE}
            },
        }
    },
)
async def list_reconciliation_findings(
    run_id: str = Path(
        description="Reconciliation run identifier.",
        examples=["FRR-20260306-0001"],
    ),
    db_session: AsyncSession = Depends(get_async_db_session),
):
    repository = ReconciliationRepository(db_session)
    findings = await repository.list_findings(run_id)
    return ReconciliationFindingListResponse(findings=findings, total=len(findings))
