from fastapi import APIRouter, Depends, HTTPException, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import (
    ActivitySummaryQueryRequest,
    ActivitySummaryResponse,
    AssetAllocationQueryRequest,
    AssetAllocationResponse,
    AssetsUnderManagementQueryRequest,
    AssetsUnderManagementResponse,
    CashBalancesQueryRequest,
    CashBalancesResponse,
    IncomeSummaryQueryRequest,
    IncomeSummaryResponse,
)
from ..services.reporting_service import ReportingService

router = APIRouter(prefix="/reporting", tags=["Wealth Reporting"])


def get_reporting_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ReportingService:
    return ReportingService(db)


@router.post(
    "/assets-under-management/query",
    response_model=AssetsUnderManagementResponse,
    summary="Query Assets Under Management",
    description=(
        "Returns assets-under-management views for a single portfolio, an explicit portfolio list, "
        "or a business unit (booking center). Designed for PB/WM dashboards and reporting packs "
        "using latest-snapshot, as-of-date semantics."
    ),
)
async def query_assets_under_management(
    request: AssetsUnderManagementQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_assets_under_management(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/asset-allocation/query",
    response_model=AssetAllocationResponse,
    summary="Query Asset Allocation",
    description=(
        "Returns allocation views grouped by Lotus-supported classification dimensions such as "
        "asset class, currency, sector, country, product type, rating, and issuer hierarchy. "
        "Optimized for interactive reporting over resolved portfolio scopes."
    ),
)
async def query_asset_allocation(
    request: AssetAllocationQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_asset_allocation(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/cash-balances/query",
    response_model=CashBalancesResponse,
    summary="Query Cash Balances",
    description=(
        "Returns portfolio cash accounts, native balances, and translated totals in portfolio "
        "currency and reporting currency for UI and reporting workflows. "
        "For large-scale export workflows, prefer a dedicated async export contract."
    ),
)
async def query_cash_balances(
    request: CashBalancesQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_cash_balances(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/income-summary/query",
    response_model=IncomeSummaryResponse,
    summary="Query Income Summary",
    description=(
        "Returns income totals for the requested reporting window and year-to-date, with values "
        "in portfolio currency and reporting currency. Income is grouped by canonical Lotus "
        "income transaction types such as dividend, interest, and cash-in-lieu."
    ),
)
async def query_income_summary(
    request: IncomeSummaryQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_income_summary(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/activity-summary/query",
    response_model=ActivitySummaryResponse,
    summary="Query Activity Summary",
    description=(
        "Returns portfolio-level flow buckets for the requested reporting window and year-to-date. "
        "The summary is intentionally scoped to portfolio flows: inflows, outflows, fees, and "
        "taxes, with values translated to portfolio currency and reporting currency."
    ),
)
async def query_activity_summary(
    request: ActivitySummaryQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_activity_summary(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
