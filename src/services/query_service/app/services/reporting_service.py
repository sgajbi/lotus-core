from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import (
    ActivityBucketSummary,
    ActivitySummaryQueryRequest,
    ActivitySummaryResponse,
    ActivitySummaryTotals,
    AllocationBucket,
    AllocationLookThroughInfo,
    AllocationView,
    AssetAllocationQueryRequest,
    AssetAllocationResponse,
    AssetsUnderManagementQueryRequest,
    AssetsUnderManagementResponse,
    AssetsUnderManagementTotals,
    CashBalancesQueryRequest,
    CashBalancesResponse,
    FlowPeriodSummary,
    IncomePeriodSummary,
    IncomeSummaryQueryRequest,
    IncomeSummaryResponse,
    IncomeSummaryTotals,
    IncomeTypeSummary,
    PortfolioActivitySummary,
    PortfolioIncomeSummary,
    PortfolioSummaryQueryRequest,
    PortfolioSummaryResponse,
    PortfolioSummarySnapshotMetadata,
    PortfolioSummaryTotals,
    ReportingPortfolioSummary,
    ReportingScope,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.reporting_repository import (
    ActivitySummaryAggregateRow,
    IncomeSummaryAggregateRow,
    InstrumentLookthroughComponentRow,
    ReportingRepository,
)
from .allocation_calculator import AllocationInputRow, calculate_allocation_views
from .cash_balance_service import CashBalanceResolver

ZERO = Decimal("0")


class ReportingService:
    def __init__(self, db: AsyncSession):
        self.repo = ReportingRepository(db)
        self._fx_cache: dict[tuple[str, str, date], Decimal] = {}
        self._cash_balance_resolver = CashBalanceResolver(
            repo=self.repo,
            convert_amount=self._convert_amount,
        )

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
        allocation_rows, look_through_info = await self._resolve_allocation_rows(
            rows=rows,
            requested_mode=request.look_through_mode,
            as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )

        allocation_result = calculate_allocation_views(
            rows=[
                AllocationInputRow(
                    instrument=instrument,
                    snapshot=snapshot,
                    market_value_reporting_currency=reporting_value,
                )
                for instrument, snapshot, reporting_value in allocation_rows
            ],
            dimensions=request.dimensions,
        )

        views = [
            AllocationView(
                dimension=view.dimension,
                total_market_value_reporting_currency=(view.total_market_value_reporting_currency),
                buckets=[
                    AllocationBucket(
                        dimension_value=bucket.dimension_value,
                        market_value_reporting_currency=(bucket.market_value_reporting_currency),
                        weight=bucket.weight,
                        position_count=bucket.position_count,
                    )
                    for bucket in view.buckets
                ],
            )
            for view in allocation_result.views
        ]

        return AssetAllocationResponse(
            scope_type=request.scope.scope_type,
            scope=request.scope,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
            total_market_value_reporting_currency=(
                allocation_result.total_market_value_reporting_currency
            ),
            look_through=look_through_info,
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
        return await self._cash_balance_resolver.build_cash_balances_response(
            portfolio=portfolio,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
            rows=rows,
        )

    async def get_portfolio_summary(
        self, request: PortfolioSummaryQueryRequest
    ) -> PortfolioSummaryResponse:
        portfolio = await self.repo.get_portfolio_by_id(request.portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio with id {request.portfolio_id} not found")

        resolved_as_of_date = request.as_of_date or await self.repo.get_latest_business_date()
        if resolved_as_of_date is None:
            raise ValueError("No business date is available for portfolio summary queries.")
        reporting_currency = request.reporting_currency or portfolio.base_currency

        rows = await self.repo.list_latest_snapshot_rows(
            portfolio_ids=[portfolio.portfolio_id],
            as_of_date=resolved_as_of_date,
        )
        cash_rows = [row for row in rows if self._cash_balance_resolver.is_cash_row(row)]
        cash_account_records = await self._cash_balance_resolver.build_cash_account_balance_records(
            portfolio=portfolio,
            cash_rows=cash_rows,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )

        total_portfolio = ZERO
        total_reporting = ZERO
        cash_portfolio = sum(
            (record.balance_portfolio_currency for record in cash_account_records),
            ZERO,
        )
        cash_reporting = sum(
            (record.balance_reporting_currency for record in cash_account_records),
            ZERO,
        )
        valued_position_count = 0
        unvalued_position_count = 0
        snapshot_date = resolved_as_of_date

        for row in rows:
            snapshot_date = max(snapshot_date, row.snapshot.date)
            portfolio_value = Decimal(str(row.snapshot.market_value or ZERO))
            reporting_value = await self._convert_amount(
                amount=portfolio_value,
                from_currency=portfolio.base_currency,
                to_currency=reporting_currency,
                as_of_date=resolved_as_of_date,
            )
            total_portfolio += portfolio_value
            total_reporting += reporting_value
            if str(row.snapshot.valuation_status or "").upper() == "UNVALUED":
                unvalued_position_count += 1
            else:
                valued_position_count += 1

        return PortfolioSummaryResponse(
            portfolio_id=portfolio.portfolio_id,
            booking_center_code=portfolio.booking_center_code,
            client_id=portfolio.client_id,
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            resolved_as_of_date=resolved_as_of_date,
            portfolio_type=portfolio.portfolio_type,
            objective=portfolio.objective,
            risk_exposure=portfolio.risk_exposure,
            status=portfolio.status,
            totals=PortfolioSummaryTotals(
                total_market_value_portfolio_currency=total_portfolio,
                total_market_value_reporting_currency=total_reporting,
                cash_balance_portfolio_currency=cash_portfolio,
                cash_balance_reporting_currency=cash_reporting,
                invested_market_value_portfolio_currency=total_portfolio - cash_portfolio,
                invested_market_value_reporting_currency=total_reporting - cash_reporting,
            ),
            snapshot_metadata=PortfolioSummarySnapshotMetadata(
                snapshot_date=snapshot_date,
                position_count=len(rows),
                cash_account_count=len(cash_account_records),
                valued_position_count=valued_position_count,
                unvalued_position_count=unvalued_position_count,
            ),
        )

    async def _resolve_allocation_rows(
        self,
        *,
        rows: list,
        requested_mode: str,
        as_of_date: date,
        reporting_currency: str,
    ) -> tuple[list[tuple[object | None, object, Decimal]], AllocationLookThroughInfo]:
        direct_rows: list[tuple[object | None, object, Decimal]] = []
        for row in rows:
            native_value = Decimal(str(row.snapshot.market_value or ZERO))
            reporting_value = await self._convert_amount(
                amount=native_value,
                from_currency=row.portfolio.base_currency,
                to_currency=reporting_currency,
                as_of_date=as_of_date,
            )
            direct_rows.append((row.instrument, row.snapshot, reporting_value))

        component_rows = await self.repo.list_instrument_lookthrough_components(
            parent_security_ids=[row.snapshot.security_id for row in rows],
            as_of_date=as_of_date,
        )
        components_by_parent: dict[str, list[InstrumentLookthroughComponentRow]] = defaultdict(list)
        for component_row in component_rows:
            components_by_parent[component_row.parent_security_id].append(component_row)
        decomposable_parent_ids = {
            parent_security_id
            for parent_security_id, components in components_by_parent.items()
            if self._can_decompose_position(components)
        }

        if requested_mode == "direct_only":
            return direct_rows, AllocationLookThroughInfo(
                requested_mode=requested_mode,
                applied_mode="direct_only",
                supported=bool(decomposable_parent_ids),
                decomposed_position_count=0,
                limitation_reason=None,
            )

        allocation_rows: list[tuple[object | None, object, Decimal]] = []
        decomposed_position_count = 0
        undecomposed_requested_count = 0

        for row in rows:
            native_value = Decimal(str(row.snapshot.market_value or ZERO))
            reporting_value = await self._convert_amount(
                amount=native_value,
                from_currency=row.portfolio.base_currency,
                to_currency=reporting_currency,
                as_of_date=as_of_date,
            )
            components = components_by_parent.get(row.snapshot.security_id, [])
            if row.snapshot.security_id not in decomposable_parent_ids:
                allocation_rows.append((row.instrument, row.snapshot, reporting_value))
                if not self._cash_balance_resolver.is_cash_row(row):
                    undecomposed_requested_count += 1
                continue

            decomposed_position_count += 1
            for component in components:
                allocation_rows.append(
                    (
                        component.component_instrument,
                        SimpleNamespace(security_id=component.component_security_id),
                        reporting_value * Decimal(str(component.component_weight)),
                    )
                )

        if decomposed_position_count == 0:
            limitation_reason: str | None = (
                "Look-through components were requested but no fully weighted source-owned "
                "decomposition set was available for the resolved holdings."
            )
            return direct_rows, AllocationLookThroughInfo(
                requested_mode=requested_mode,
                applied_mode="direct_only",
                supported=False,
                decomposed_position_count=0,
                limitation_reason=limitation_reason,
            )

        limitation_reason = None
        if undecomposed_requested_count:
            limitation_reason = (
                "Look-through was applied where complete component weights were available; "
                "remaining positions stayed at direct-holding level."
            )
        return allocation_rows, AllocationLookThroughInfo(
            requested_mode=requested_mode,
            applied_mode="prefer_look_through",
            supported=True,
            decomposed_position_count=decomposed_position_count,
            limitation_reason=limitation_reason,
        )

    @staticmethod
    def _can_decompose_position(
        components: list[InstrumentLookthroughComponentRow],
    ) -> bool:
        if not components:
            return False
        total_weight = sum(
            (Decimal(str(component.component_weight)) for component in components),
            ZERO,
        )
        return abs(total_weight - Decimal("1")) <= Decimal("0.000001")

    async def get_income_summary(self, request: IncomeSummaryQueryRequest) -> IncomeSummaryResponse:
        portfolios, _ = await self._resolve_scope_portfolios_and_date(
            request.scope,
            request.window.end_date,
        )
        reporting_currency = await self._resolve_reporting_currency(
            scope=request.scope,
            portfolios=portfolios,
            requested_reporting_currency=request.reporting_currency,
        )
        rows = await self.repo.list_income_summary_rows(
            portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
            start_date=request.window.start_date,
            end_date=request.window.end_date,
            income_types=request.income_types,
        )

        include_scope_portfolio_currency = request.scope.scope_type == "portfolio"
        scope_requested = self._new_income_metric()
        scope_ytd = self._new_income_metric()
        per_portfolio_requested: dict[str, dict[str, Decimal | int]] = defaultdict(
            self._new_income_metric
        )
        per_portfolio_ytd: dict[str, dict[str, Decimal | int]] = defaultdict(
            self._new_income_metric
        )
        per_portfolio_income_type_requested: dict[str, dict[str, dict[str, Decimal | int]]] = (
            defaultdict(lambda: defaultdict(self._new_income_metric))
        )
        per_portfolio_income_type_ytd: dict[str, dict[str, dict[str, Decimal | int]]] = defaultdict(
            lambda: defaultdict(self._new_income_metric)
        )

        for row in rows:
            await self._accumulate_income_row(
                accumulator=scope_requested,
                row=row,
                period="requested",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=include_scope_portfolio_currency,
            )
            await self._accumulate_income_row(
                accumulator=scope_ytd,
                row=row,
                period="ytd",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=include_scope_portfolio_currency,
            )
            await self._accumulate_income_row(
                accumulator=per_portfolio_requested[row.portfolio_id],
                row=row,
                period="requested",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=True,
            )
            await self._accumulate_income_row(
                accumulator=per_portfolio_ytd[row.portfolio_id],
                row=row,
                period="ytd",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=True,
            )
            await self._accumulate_income_row(
                accumulator=per_portfolio_income_type_requested[row.portfolio_id][row.income_type],
                row=row,
                period="requested",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=True,
            )
            await self._accumulate_income_row(
                accumulator=per_portfolio_income_type_ytd[row.portfolio_id][row.income_type],
                row=row,
                period="ytd",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=True,
            )

        portfolio_rows: list[PortfolioIncomeSummary] = []
        for portfolio in portfolios:
            income_type_rows = []
            for income_type in request.income_types:
                income_type_rows.append(
                    IncomeTypeSummary(
                        income_type=income_type,
                        requested_window=self._build_income_period_summary(
                            per_portfolio_income_type_requested[portfolio.portfolio_id][
                                income_type
                            ],
                            include_portfolio_currency=True,
                        ),
                        year_to_date=self._build_income_period_summary(
                            per_portfolio_income_type_ytd[portfolio.portfolio_id][income_type],
                            include_portfolio_currency=True,
                        ),
                    )
                )
            portfolio_rows.append(
                PortfolioIncomeSummary(
                    portfolio_id=portfolio.portfolio_id,
                    booking_center_code=portfolio.booking_center_code,
                    client_id=portfolio.client_id,
                    portfolio_currency=portfolio.base_currency,
                    requested_window=self._build_income_period_summary(
                        per_portfolio_requested[portfolio.portfolio_id],
                        include_portfolio_currency=True,
                    ),
                    year_to_date=self._build_income_period_summary(
                        per_portfolio_ytd[portfolio.portfolio_id],
                        include_portfolio_currency=True,
                    ),
                    income_types=income_type_rows,
                )
            )

        return IncomeSummaryResponse(
            scope_type=request.scope.scope_type,
            scope=request.scope,
            resolved_window=request.window,
            reporting_currency=reporting_currency,
            totals=IncomeSummaryTotals(
                portfolio_count=len(portfolios),
                requested_window=self._build_income_period_summary(
                    scope_requested,
                    include_portfolio_currency=include_scope_portfolio_currency,
                ),
                year_to_date=self._build_income_period_summary(
                    scope_ytd,
                    include_portfolio_currency=include_scope_portfolio_currency,
                ),
            ),
            portfolios=portfolio_rows,
            **source_data_product_runtime_metadata(
                as_of_date=request.window.end_date,
                latest_evidence_timestamp=self._latest_aggregate_evidence_timestamp(rows),
            ),
        )

    async def get_activity_summary(
        self, request: ActivitySummaryQueryRequest
    ) -> ActivitySummaryResponse:
        portfolios, _ = await self._resolve_scope_portfolios_and_date(
            request.scope,
            request.window.end_date,
        )
        reporting_currency = await self._resolve_reporting_currency(
            scope=request.scope,
            portfolios=portfolios,
            requested_reporting_currency=request.reporting_currency,
        )
        rows = await self.repo.list_activity_summary_rows(
            portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )

        buckets = ["INFLOWS", "OUTFLOWS", "FEES", "TAXES"]
        include_scope_portfolio_currency = request.scope.scope_type == "portfolio"
        scope_requested: dict[str, dict[str, Decimal | int]] = defaultdict(self._new_flow_metric)
        scope_ytd: dict[str, dict[str, Decimal | int]] = defaultdict(self._new_flow_metric)
        per_portfolio_requested: dict[str, dict[str, dict[str, Decimal | int]]] = defaultdict(
            lambda: defaultdict(self._new_flow_metric)
        )
        per_portfolio_ytd: dict[str, dict[str, dict[str, Decimal | int]]] = defaultdict(
            lambda: defaultdict(self._new_flow_metric)
        )

        for row in rows:
            await self._accumulate_flow_row(
                accumulator=scope_requested[row.bucket],
                row=row,
                period="requested",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=include_scope_portfolio_currency,
            )
            await self._accumulate_flow_row(
                accumulator=scope_ytd[row.bucket],
                row=row,
                period="ytd",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=include_scope_portfolio_currency,
            )
            await self._accumulate_flow_row(
                accumulator=per_portfolio_requested[row.portfolio_id][row.bucket],
                row=row,
                period="requested",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=True,
            )
            await self._accumulate_flow_row(
                accumulator=per_portfolio_ytd[row.portfolio_id][row.bucket],
                row=row,
                period="ytd",
                reporting_currency=reporting_currency,
                as_of_date=request.window.end_date,
                include_portfolio_currency=True,
            )

        portfolio_rows: list[PortfolioActivitySummary] = []
        for portfolio in portfolios:
            bucket_rows = [
                ActivityBucketSummary(
                    bucket=bucket,
                    requested_window=self._build_flow_period_summary(
                        per_portfolio_requested[portfolio.portfolio_id][bucket],
                        include_portfolio_currency=True,
                    ),
                    year_to_date=self._build_flow_period_summary(
                        per_portfolio_ytd[portfolio.portfolio_id][bucket],
                        include_portfolio_currency=True,
                    ),
                )
                for bucket in buckets
            ]
            portfolio_rows.append(
                PortfolioActivitySummary(
                    portfolio_id=portfolio.portfolio_id,
                    booking_center_code=portfolio.booking_center_code,
                    client_id=portfolio.client_id,
                    portfolio_currency=portfolio.base_currency,
                    buckets=bucket_rows,
                )
            )

        return ActivitySummaryResponse(
            scope_type=request.scope.scope_type,
            scope=request.scope,
            resolved_window=request.window,
            reporting_currency=reporting_currency,
            totals=ActivitySummaryTotals(
                portfolio_count=len(portfolios),
                buckets=[
                    ActivityBucketSummary(
                        bucket=bucket,
                        requested_window=self._build_flow_period_summary(
                            scope_requested[bucket],
                            include_portfolio_currency=include_scope_portfolio_currency,
                        ),
                        year_to_date=self._build_flow_period_summary(
                            scope_ytd[bucket],
                            include_portfolio_currency=include_scope_portfolio_currency,
                        ),
                    )
                    for bucket in buckets
                ],
            ),
            portfolios=portfolio_rows,
            **source_data_product_runtime_metadata(
                as_of_date=request.window.end_date,
                latest_evidence_timestamp=self._latest_aggregate_evidence_timestamp(rows),
            ),
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
        portfolios: list[Any],
        requested_reporting_currency: str | None,
    ) -> str:
        if requested_reporting_currency:
            return requested_reporting_currency
        if scope.scope_type == "portfolio":
            return str(portfolios[0].base_currency)
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
        rate = Decimal(str(rate))
        self._fx_cache[cache_key] = rate
        return rate

    @staticmethod
    def _new_income_metric() -> dict[str, Decimal | int]:
        return {
            "transaction_count": 0,
            "gross_portfolio": ZERO,
            "gross_reporting": ZERO,
            "withholding_portfolio": ZERO,
            "withholding_reporting": ZERO,
            "other_portfolio": ZERO,
            "other_reporting": ZERO,
            "net_portfolio": ZERO,
            "net_reporting": ZERO,
        }

    @staticmethod
    def _latest_snapshot_evidence_timestamp(rows: list[Any]) -> datetime | None:
        timestamps: list[datetime] = []
        for row in rows:
            snapshot = getattr(row, "snapshot", None)
            for candidate in (
                getattr(snapshot, "updated_at", None),
                getattr(snapshot, "created_at", None),
            ):
                if isinstance(candidate, datetime):
                    timestamps.append(candidate)
        return max(timestamps) if timestamps else None

    @staticmethod
    def _latest_aggregate_evidence_timestamp(rows: list[Any]) -> datetime | None:
        timestamps = [
            timestamp
            for row in rows
            if isinstance(timestamp := getattr(row, "latest_evidence_timestamp", None), datetime)
        ]
        return max(timestamps) if timestamps else None

    @staticmethod
    def _new_flow_metric() -> dict[str, Decimal | int]:
        return {
            "transaction_count": 0,
            "amount_portfolio": ZERO,
            "amount_reporting": ZERO,
        }

    async def _accumulate_income_row(
        self,
        *,
        accumulator: dict[str, Decimal | int],
        row: IncomeSummaryAggregateRow,
        period: str,
        reporting_currency: str,
        as_of_date: date,
        include_portfolio_currency: bool = False,
    ) -> None:
        count = (
            row.requested_transaction_count if period == "requested" else row.ytd_transaction_count
        )
        gross = row.requested_gross_amount if period == "requested" else row.ytd_gross_amount
        withholding = (
            row.requested_withholding_tax if period == "requested" else row.ytd_withholding_tax
        )
        other_deductions = (
            row.requested_other_deductions if period == "requested" else row.ytd_other_deductions
        )
        net = row.requested_net_amount if period == "requested" else row.ytd_net_amount

        portfolio_gross = await self._convert_amount(
            amount=gross,
            from_currency=row.source_currency,
            to_currency=row.portfolio_currency,
            as_of_date=as_of_date,
        )
        portfolio_withholding = await self._convert_amount(
            amount=withholding,
            from_currency=row.source_currency,
            to_currency=row.portfolio_currency,
            as_of_date=as_of_date,
        )
        portfolio_other = await self._convert_amount(
            amount=other_deductions,
            from_currency=row.source_currency,
            to_currency=row.portfolio_currency,
            as_of_date=as_of_date,
        )
        portfolio_net = await self._convert_amount(
            amount=net,
            from_currency=row.source_currency,
            to_currency=row.portfolio_currency,
            as_of_date=as_of_date,
        )
        reporting_gross = await self._convert_amount(
            amount=gross,
            from_currency=row.source_currency,
            to_currency=reporting_currency,
            as_of_date=as_of_date,
        )
        reporting_withholding = await self._convert_amount(
            amount=withholding,
            from_currency=row.source_currency,
            to_currency=reporting_currency,
            as_of_date=as_of_date,
        )
        reporting_other = await self._convert_amount(
            amount=other_deductions,
            from_currency=row.source_currency,
            to_currency=reporting_currency,
            as_of_date=as_of_date,
        )
        reporting_net = await self._convert_amount(
            amount=net,
            from_currency=row.source_currency,
            to_currency=reporting_currency,
            as_of_date=as_of_date,
        )

        accumulator["transaction_count"] = int(accumulator["transaction_count"]) + count
        accumulator["gross_reporting"] = Decimal(accumulator["gross_reporting"]) + reporting_gross
        accumulator["withholding_reporting"] = (
            Decimal(accumulator["withholding_reporting"]) + reporting_withholding
        )
        accumulator["other_reporting"] = Decimal(accumulator["other_reporting"]) + reporting_other
        accumulator["net_reporting"] = Decimal(accumulator["net_reporting"]) + reporting_net
        if include_portfolio_currency:
            accumulator["gross_portfolio"] = (
                Decimal(accumulator["gross_portfolio"]) + portfolio_gross
            )
            accumulator["withholding_portfolio"] = (
                Decimal(accumulator["withholding_portfolio"]) + portfolio_withholding
            )
            accumulator["other_portfolio"] = (
                Decimal(accumulator["other_portfolio"]) + portfolio_other
            )
            accumulator["net_portfolio"] = Decimal(accumulator["net_portfolio"]) + portfolio_net

    async def _accumulate_flow_row(
        self,
        *,
        accumulator: dict[str, Decimal | int],
        row: ActivitySummaryAggregateRow,
        period: str,
        reporting_currency: str,
        as_of_date: date,
        include_portfolio_currency: bool = False,
    ) -> None:
        count = (
            row.requested_transaction_count if period == "requested" else row.ytd_transaction_count
        )
        amount = row.requested_amount if period == "requested" else row.ytd_amount
        portfolio_amount = await self._convert_amount(
            amount=amount,
            from_currency=row.source_currency,
            to_currency=row.portfolio_currency,
            as_of_date=as_of_date,
        )
        reporting_amount = await self._convert_amount(
            amount=amount,
            from_currency=row.source_currency,
            to_currency=reporting_currency,
            as_of_date=as_of_date,
        )
        accumulator["transaction_count"] = int(accumulator["transaction_count"]) + count
        accumulator["amount_reporting"] = (
            Decimal(accumulator["amount_reporting"]) + reporting_amount
        )
        if include_portfolio_currency:
            accumulator["amount_portfolio"] = (
                Decimal(accumulator["amount_portfolio"]) + portfolio_amount
            )

    @staticmethod
    def _build_income_period_summary(
        accumulator: dict[str, Decimal | int],
        *,
        include_portfolio_currency: bool,
    ) -> IncomePeriodSummary:
        return IncomePeriodSummary(
            transaction_count=int(accumulator["transaction_count"]),
            gross_amount_portfolio_currency=(
                Decimal(accumulator["gross_portfolio"]) if include_portfolio_currency else None
            ),
            gross_amount_reporting_currency=Decimal(accumulator["gross_reporting"]),
            withholding_tax_portfolio_currency=(
                Decimal(accumulator["withholding_portfolio"])
                if include_portfolio_currency
                else None
            ),
            withholding_tax_reporting_currency=Decimal(accumulator["withholding_reporting"]),
            other_deductions_portfolio_currency=(
                Decimal(accumulator["other_portfolio"]) if include_portfolio_currency else None
            ),
            other_deductions_reporting_currency=Decimal(accumulator["other_reporting"]),
            net_amount_portfolio_currency=(
                Decimal(accumulator["net_portfolio"]) if include_portfolio_currency else None
            ),
            net_amount_reporting_currency=Decimal(accumulator["net_reporting"]),
        )

    @staticmethod
    def _build_flow_period_summary(
        accumulator: dict[str, Decimal | int],
        *,
        include_portfolio_currency: bool,
    ) -> FlowPeriodSummary:
        return FlowPeriodSummary(
            transaction_count=int(accumulator["transaction_count"]),
            amount_portfolio_currency=(
                Decimal(accumulator["amount_portfolio"]) if include_portfolio_currency else None
            ),
            amount_reporting_currency=Decimal(accumulator["amount_reporting"]),
        )
