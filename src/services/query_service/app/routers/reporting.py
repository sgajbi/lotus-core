from fastapi import APIRouter, Depends, HTTPException, status
from portfolio_common.db import get_async_db_session
from portfolio_common.source_data_products import source_data_product_openapi_extra
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
    HoldingsSnapshotQueryRequest,
    HoldingsSnapshotResponse,
    IncomeSummaryQueryRequest,
    IncomeSummaryResponse,
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
    "/cash-balances/query",
    response_model=CashBalancesResponse,
    summary="Query Cash Balances",
    description=(
        "What: Return cash-account balances and translated cash totals for one portfolio.\n"
        "How: Publishes per-account native balances together with portfolio-currency and "
        "reporting-currency restatement for the resolved as-of date.\n"
        "When: Use this compatibility route only when a downstream consumer genuinely needs "
        "per-account cash balances or translated cash totals that are not yet published by the "
        "strategic HoldingsAsOf operational read. This route remains a pre-live convenience "
        "shape for the RFC-0083 HoldingsAsOf source-data product and should not absorb broader "
        "holdings, performance, or reporting composition behavior. For large-scale export "
        "workflows, prefer a dedicated async export contract."
    ),
    deprecated=True,
    openapi_extra=source_data_product_openapi_extra("HoldingsAsOf"),
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


@router.post(
    "/holdings-snapshot/query",
    response_model=HoldingsSnapshotResponse,
    summary="Query Historical Holdings Snapshot",
    description=(
        "Returns a true historical as-of holdings snapshot for one portfolio with reporting-"
        "currency restatement and portfolio-workspace classifications. Use this contract for "
        "UI holdings views and reporting extracts that need region-aware, restated holdings rows. "
        "This route is a pre-live convenience shape for the RFC-0083 HoldingsAsOf source-data "
        "product. New consumers should bind to the named source-data product contract when it is "
        "available."
    ),
    deprecated=True,
    openapi_extra=source_data_product_openapi_extra("HoldingsAsOf"),
)
async def query_holdings_snapshot(
    request: HoldingsSnapshotQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_holdings_snapshot(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/income-summary/query",
    response_model=IncomeSummaryResponse,
    summary="Query Income Summary",
    description=(
        "Returns income totals for the requested reporting window and year-to-date, with values "
        "in portfolio currency and reporting currency. Income is grouped by canonical Lotus "
        "income transaction types such as dividend, interest, and cash-in-lieu. This route is a "
        "pre-live convenience shape for the RFC-0083 TransactionLedgerWindow source-data product. "
        "New consumers should bind to the named source-data product contract when it is available."
    ),
    deprecated=True,
    openapi_extra=source_data_product_openapi_extra("TransactionLedgerWindow"),
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
        "taxes, with values translated to portfolio currency and reporting currency. This route is "
        "a pre-live convenience shape for the RFC-0083 TransactionLedgerWindow source-data product. "
        "New consumers should bind to the named source-data product contract when it is available."
    ),
    deprecated=True,
    openapi_extra=source_data_product_openapi_extra("TransactionLedgerWindow"),
)
async def query_activity_summary(
    request: ActivitySummaryQueryRequest,
    service: ReportingService = Depends(get_reporting_service),
):
    try:
        return await service.get_activity_summary(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
