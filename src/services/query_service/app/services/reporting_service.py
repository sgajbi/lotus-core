from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import (
    AllocationBucket,
    AllocationView,
    AssetAllocationQueryRequest,
    AssetAllocationResponse,
    AssetsUnderManagementQueryRequest,
    AssetsUnderManagementResponse,
    AssetsUnderManagementTotals,
    CashAccountBalanceRecord,
    CashBalancesQueryRequest,
    CashBalancesResponse,
    CashBalancesTotals,
    ReportingPortfolioSummary,
    ReportingScope,
)
from ..repositories.reporting_repository import ReportingRepository

ZERO = Decimal("0")
CASH_ASSET_CLASS = "CASH"
ALLOCATION_DIMENSION_ACCESSORS = {
    "asset_class": lambda instrument, snapshot: instrument.asset_class if instrument else None,
    "currency": lambda instrument, snapshot: (
        instrument.currency if instrument and instrument.currency else snapshot.security_id
    ),
    "sector": lambda instrument, snapshot: instrument.sector if instrument else None,
    "country": lambda instrument, snapshot: instrument.country_of_risk if instrument else None,
    "product_type": lambda instrument, snapshot: instrument.product_type if instrument else None,
    "rating": lambda instrument, snapshot: instrument.rating if instrument else None,
    "issuer_id": lambda instrument, snapshot: instrument.issuer_id if instrument else None,
    "issuer_name": lambda instrument, snapshot: instrument.issuer_name if instrument else None,
    "ultimate_parent_issuer_id": (
        lambda instrument, snapshot: instrument.ultimate_parent_issuer_id if instrument else None
    ),
    "ultimate_parent_issuer_name": (
        lambda instrument, snapshot: instrument.ultimate_parent_issuer_name if instrument else None
    ),
}


class ReportingService:
    def __init__(self, db: AsyncSession):
        self.repo = ReportingRepository(db)
        self._fx_cache: dict[tuple[str, str, date], Decimal] = {}

    async def get_assets_under_management(
        self, request: AssetsUnderManagementQueryRequest
    ) -> AssetsUnderManagementResponse:
        portfolios, resolved_as_of_date = await self._resolve_scope_portfolios_and_date(
            request.scope,
            request.as_of_date,
        )
        reporting_currency = await self._resolve_reporting_currency(
            scope=request.scope,
            portfolios=portfolios,
            requested_reporting_currency=request.reporting_currency,
        )
        rows = await self.repo.list_latest_snapshot_rows(
            portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
            as_of_date=resolved_as_of_date,
        )

        per_portfolio_reporting: dict[str, Decimal] = defaultdict(lambda: ZERO)
        per_portfolio_native: dict[str, Decimal] = defaultdict(lambda: ZERO)
        per_portfolio_positions: dict[str, int] = defaultdict(int)

        for row in rows:
            native_value = Decimal(str(row.snapshot.market_value or ZERO))
            reporting_value = await self._convert_amount(
                amount=native_value,
                from_currency=row.portfolio.base_currency,
                to_currency=reporting_currency,
                as_of_date=resolved_as_of_date,
            )
            per_portfolio_native[row.portfolio.portfolio_id] += native_value
            per_portfolio_reporting[row.portfolio.portfolio_id] += reporting_value
            per_portfolio_positions[row.portfolio.portfolio_id] += 1

        portfolio_summaries: list[ReportingPortfolioSummary] = []
        total_positions = 0
        total_aum_reporting = ZERO
        for portfolio in portfolios:
            total_positions += per_portfolio_positions[portfolio.portfolio_id]
            total_aum_reporting += per_portfolio_reporting[portfolio.portfolio_id]
            portfolio_summaries.append(
                ReportingPortfolioSummary(
                    portfolio_id=portfolio.portfolio_id,
                    booking_center_code=portfolio.booking_center_code,
                    client_id=portfolio.client_id,
                    portfolio_currency=portfolio.base_currency,
                    aum_portfolio_currency=(
                        per_portfolio_native[portfolio.portfolio_id]
                        if request.scope.scope_type == "portfolio"
                        else None
                    ),
                    aum_reporting_currency=per_portfolio_reporting[portfolio.portfolio_id],
                    position_count=per_portfolio_positions[portfolio.portfolio_id],
                )
            )

        return AssetsUnderManagementResponse(
            scope_type=request.scope.scope_type,
            scope=request.scope,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
            totals=AssetsUnderManagementTotals(
                portfolio_count=len(portfolios),
                position_count=total_positions,
                aum_reporting_currency=total_aum_reporting,
            ),
            portfolios=portfolio_summaries,
        )

    async def get_asset_allocation(
        self, request: AssetAllocationQueryRequest
    ) -> AssetAllocationResponse:
        portfolios, resolved_as_of_date = await self._resolve_scope_portfolios_and_date(
            request.scope,
            request.as_of_date,
        )
        reporting_currency = await self._resolve_reporting_currency(
            scope=request.scope,
            portfolios=portfolios,
            requested_reporting_currency=request.reporting_currency,
        )
        rows = await self.repo.list_latest_snapshot_rows(
            portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
            as_of_date=resolved_as_of_date,
        )

        total_market_value = ZERO
        views_payload: dict[str, dict[str, Decimal]] = {
            dimension: defaultdict(lambda: ZERO) for dimension in request.dimensions
        }
        views_position_counts: dict[str, dict[str, int]] = {
            dimension: defaultdict(int) for dimension in request.dimensions
        }

        for row in rows:
            native_value = Decimal(str(row.snapshot.market_value or ZERO))
            reporting_value = await self._convert_amount(
                amount=native_value,
                from_currency=row.portfolio.base_currency,
                to_currency=reporting_currency,
                as_of_date=resolved_as_of_date,
            )
            total_market_value += reporting_value
            for dimension in request.dimensions:
                accessor = ALLOCATION_DIMENSION_ACCESSORS[dimension]
                raw_value = accessor(row.instrument, row.snapshot)
                bucket_key = str(raw_value or "UNCLASSIFIED")
                views_payload[dimension][bucket_key] += reporting_value
                views_position_counts[dimension][bucket_key] += 1

        views: list[AllocationView] = []
        for dimension in request.dimensions:
            buckets = []
            for bucket_key, bucket_value in sorted(views_payload[dimension].items()):
                buckets.append(
                    AllocationBucket(
                        dimension_value=bucket_key,
                        market_value_reporting_currency=bucket_value,
                        weight=(bucket_value / total_market_value if total_market_value else ZERO),
                        position_count=views_position_counts[dimension][bucket_key],
                    )
                )
            views.append(
                AllocationView(
                    dimension=dimension,
                    total_market_value_reporting_currency=total_market_value,
                    buckets=buckets,
                )
            )

        return AssetAllocationResponse(
            scope_type=request.scope.scope_type,
            scope=request.scope,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
            total_market_value_reporting_currency=total_market_value,
            views=views,
        )

    async def get_cash_balances(self, request: CashBalancesQueryRequest) -> CashBalancesResponse:
        portfolio = await self.repo.get_portfolio_by_id(request.portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio with id {request.portfolio_id} not found")

        resolved_as_of_date = request.as_of_date or await self.repo.get_latest_business_date()
        if resolved_as_of_date is None:
            raise ValueError("No business date is available for cash balance queries.")
        reporting_currency = request.reporting_currency or portfolio.base_currency

        rows = await self.repo.list_latest_snapshot_rows(
            portfolio_ids=[portfolio.portfolio_id],
            as_of_date=resolved_as_of_date,
        )
        cash_rows = [
            row
            for row in rows
            if row.instrument is not None
            and str(row.instrument.asset_class or "").upper() == CASH_ASSET_CLASS
        ]
        cash_account_map = await self.repo.get_latest_cash_account_ids(
            portfolio_id=portfolio.portfolio_id,
            cash_security_ids=[row.snapshot.security_id for row in cash_rows],
            as_of_date=resolved_as_of_date,
        )

        account_records: list[CashAccountBalanceRecord] = []
        total_portfolio_currency = ZERO
        total_reporting_currency = ZERO
        for row in cash_rows:
            account_currency = row.instrument.currency or portfolio.base_currency
            native_source_value = (
                row.snapshot.market_value_local or row.snapshot.market_value or ZERO
            )
            native_balance = Decimal(str(native_source_value))
            portfolio_balance = Decimal(str(row.snapshot.market_value or ZERO))
            reporting_balance = await self._convert_amount(
                amount=portfolio_balance,
                from_currency=portfolio.base_currency,
                to_currency=reporting_currency,
                as_of_date=resolved_as_of_date,
            )
            total_portfolio_currency += portfolio_balance
            total_reporting_currency += reporting_balance
            account_records.append(
                CashAccountBalanceRecord(
                    cash_account_id=(
                        cash_account_map.get(row.snapshot.security_id)
                        or row.snapshot.security_id
                    ),
                    instrument_id=row.instrument.security_id,
                    security_id=row.snapshot.security_id,
                    account_currency=account_currency,
                    instrument_name=row.instrument.name,
                    balance_account_currency=native_balance,
                    balance_portfolio_currency=portfolio_balance,
                    balance_reporting_currency=reporting_balance,
                )
            )

        return CashBalancesResponse(
            portfolio_id=portfolio.portfolio_id,
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            resolved_as_of_date=resolved_as_of_date,
            totals=CashBalancesTotals(
                cash_account_count=len(account_records),
                total_balance_portfolio_currency=total_portfolio_currency,
                total_balance_reporting_currency=total_reporting_currency,
            ),
            cash_accounts=account_records,
        )

    async def _resolve_scope_portfolios_and_date(
        self,
        scope: ReportingScope,
        requested_as_of_date: date | None,
    ) -> tuple[list, date]:
        resolved_as_of_date = requested_as_of_date or await self.repo.get_latest_business_date()
        if resolved_as_of_date is None:
            raise ValueError("No business date is available for reporting queries.")

        portfolios = await self.repo.list_portfolios(
            portfolio_id=scope.portfolio_id,
            portfolio_ids=scope.portfolio_ids or None,
            booking_center_code=scope.booking_center_code,
        )
        if not portfolios:
            raise ValueError("No portfolios matched the requested reporting scope.")
        return portfolios, resolved_as_of_date

    async def _resolve_reporting_currency(
        self,
        *,
        scope: ReportingScope,
        portfolios: list[object],
        requested_reporting_currency: str | None,
    ) -> str:
        if requested_reporting_currency:
            return requested_reporting_currency
        if scope.scope_type == "portfolio":
            return portfolios[0].base_currency
        raise ValueError(
            "reporting_currency is required for portfolio-list and business-unit reporting queries."
        )

    async def _convert_amount(
        self,
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        if from_currency == to_currency:
            return amount
        rate = await self._get_fx_rate(from_currency, to_currency, as_of_date)
        return amount * rate

    async def _get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        cache_key = (from_currency, to_currency, as_of_date)
        if cache_key in self._fx_cache:
            return self._fx_cache[cache_key]
        rate = await self.repo.get_latest_fx_rate(
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )
        if rate is None:
            raise ValueError(
                f"FX rate not found for {from_currency}/{to_currency} as of {as_of_date}."
            )
        self._fx_cache[cache_key] = rate
        return rate
