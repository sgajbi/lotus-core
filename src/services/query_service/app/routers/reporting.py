from fastapi import APIRouter, Depends, HTTPException, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import (
    AssetAllocationQueryRequest,
    AssetAllocationResponse,
    AssetsUnderManagementQueryRequest,
    AssetsUnderManagementResponse,
    PortfolioSummaryQueryRequest,
    PortfolioSummaryResponse,
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
        "What: Return source-owned assets-under-management views for a resolved reporting scope.\n"
        "How: Resolves latest-snapshot or explicit as-of-date holdings totals for a single "
        "portfolio, portfolio list, or business unit, with optional reporting-currency "
        "restatement.\n"
        "When: Use this contract when a downstream consumer needs AUM totals and per-portfolio "
        "AUM breakdowns rather than broad holdings state or summary composition. Prefer this "
        "route over reconstructing AUM from holdings rows when the downstream need is a governed "
        "AUM figure."
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
        "What: Return the strategic allocation views for a resolved reporting scope.\n"
        "How: Computes reporting-currency allocation buckets across Lotus-supported "
        "classification dimensions such as asset class, currency, sector, country, region, "
        "product type, rating, and issuer hierarchy, with explicit look-through capability "
        "metadata.\n"
        "When: Use this contract when a downstream consumer needs allocation buckets rather than "
        "broad state publication. Prefer this route over mining allocation views from "
        "`core-snapshot` when the need is report-ready or UI-ready allocation analysis."
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
    "/portfolio-summary/query",
    response_model=PortfolioSummaryResponse,
    summary="Query Portfolio Summary Snapshot",
    description=(
        "What: Return the strategic historical portfolio summary for one portfolio and as-of "
        "date.\n"
        "How: Resolves snapshot-backed holdings totals, cash versus invested split, and summary "
        "coverage metadata with reporting-currency restatement.\n"
        "When: Use this contract when UI or reporting consumers need a restated summary in "
        "portfolio currency and reporting currency without rebuilding holdings totals client-side. "
        "Prefer this route over downstream reconstruction from holdings rows or `core-snapshot` "
        "when the consumer needs summary figures rather than sectioned source-state payloads. "
        "This is the correct lotus-core summary seam for report-ready wealth totals; it should not "
        "absorb performance, risk, or narrative reporting ownership."
    ),
)
async def query_portfolio_summary(
    request: PortfolioSummaryQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_portfolio_summary(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


