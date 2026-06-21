from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reporting_dto import (
    AllocationBucket,
    AllocationLookThroughInfo,
    AllocationView,
    AssetAllocationQueryRequest,
    AssetAllocationResponse,
    AssetsUnderManagementQueryRequest,
    AssetsUnderManagementResponse,
    AssetsUnderManagementTotals,
    PortfolioSummaryQueryRequest,
    PortfolioSummaryResponse,
    PortfolioSummarySnapshotMetadata,
    PortfolioSummaryTotals,
    ReportingPortfolioSummary,
    ReportingScope,
)
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.reporting_repository import (
    InstrumentLookthroughComponentRow,
    ReportingRepository,
)
from .allocation_calculator import AllocationInputRow, calculate_allocation_views
from .cash_balance_service import CashBalanceResolver
from .control_code_normalization import normalize_control_code
from .decimal_amounts import decimal_or_none, decimal_or_zero
from .fx_conversion import CachedFxRateConverter

ZERO = Decimal("0")
UNVALUED_STATUS = "UNVALUED"
ResolvedAllocationRow = tuple[Any, str | None, Decimal]
AllocationOutputRow = tuple[object | None, object, Decimal]


def _allocation_parent_security_ids(rows: list[Any]) -> tuple[list[str], list[str | None]]:
    parent_security_ids: list[str] = []
    row_parent_security_ids: list[str | None] = []
    for row in rows:
        parent_security_id = normalize_security_id(row.snapshot.security_id)
        if parent_security_id:
            parent_security_ids.append(parent_security_id)
        row_parent_security_ids.append(parent_security_id)
    return list(dict.fromkeys(parent_security_ids)), row_parent_security_ids


def _resolved_allocation_rows(
    *,
    reporting_values: list[tuple[Any, Decimal, Decimal]],
    row_parent_security_ids: list[str | None],
) -> list[ResolvedAllocationRow]:
    return [
        (row, parent_security_id, reporting_value)
        for (row, _native_value, reporting_value), parent_security_id in zip(
            reporting_values,
            row_parent_security_ids,
            strict=True,
        )
    ]


def _direct_allocation_rows(
    resolved_rows: list[ResolvedAllocationRow],
) -> list[AllocationOutputRow]:
    return [
        (row.instrument, row.snapshot, reporting_value)
        for row, _parent_security_id, reporting_value in resolved_rows
    ]


def _components_by_parent(
    component_rows: list[InstrumentLookthroughComponentRow],
) -> dict[str, list[InstrumentLookthroughComponentRow]]:
    components_by_parent: dict[str, list[InstrumentLookthroughComponentRow]] = defaultdict(list)
    for component_row in component_rows:
        components_by_parent[normalize_security_id(component_row.parent_security_id)].append(
            component_row
        )
    return components_by_parent


def _direct_only_lookthrough_info(
    *, requested_mode: str, supported: bool
) -> AllocationLookThroughInfo:
    return AllocationLookThroughInfo(
        requested_mode=requested_mode,
        applied_mode="direct_only",
        supported=supported,
        decomposed_position_count=0,
        limitation_reason=None,
    )


def _unsupported_lookthrough_info(*, requested_mode: str) -> AllocationLookThroughInfo:
    limitation_reason = (
        "Look-through components were requested but no fully weighted source-owned "
        "decomposition set was available for the resolved holdings."
    )
    return AllocationLookThroughInfo(
        requested_mode=requested_mode,
        applied_mode="direct_only",
        supported=False,
        decomposed_position_count=0,
        limitation_reason=limitation_reason,
    )


def _applied_lookthrough_info(
    *,
    requested_mode: str,
    decomposed_position_count: int,
    undecomposed_requested_count: int,
) -> AllocationLookThroughInfo:
    limitation_reason = None
    if undecomposed_requested_count:
        limitation_reason = (
            "Look-through was applied where complete component weights were available; "
            "remaining positions stayed at direct-holding level."
        )
    return AllocationLookThroughInfo(
        requested_mode=requested_mode,
        applied_mode="prefer_look_through",
        supported=True,
        decomposed_position_count=decomposed_position_count,
        limitation_reason=limitation_reason,
    )


def _component_weights(
    components: list[InstrumentLookthroughComponentRow],
) -> list[Decimal | None]:
    return [ReportingService._component_weight(component) for component in components]


def _complete_component_weight_total(weights: list[Decimal | None]) -> Decimal | None:
    complete_weights = [weight for weight in weights if weight is not None]
    if len(complete_weights) != len(weights) or not complete_weights:
        return None
    return sum(complete_weights, ZERO)


class ReportingService:
    def __init__(self, db: AsyncSession):
        self.repo = ReportingRepository(db)
        self._fx_converter = CachedFxRateConverter(self.repo)
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

        row_reporting_values = await self._snapshot_reporting_values(
            rows=rows,
            as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )

        for row, native_value, reporting_value in row_reporting_values:
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
                    portfolio_currency=normalize_currency_code(str(portfolio.base_currency)),
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

    async def get_portfolio_summary(
        self, request: PortfolioSummaryQueryRequest
    ) -> PortfolioSummaryResponse:
        portfolio = await self.repo.get_portfolio_by_id(request.portfolio_id)
        if portfolio is None:
            raise LookupError(f"Portfolio with id {request.portfolio_id} not found")
        resolved_as_of_date = (
            await self.repo.get_latest_business_date()
            if request.as_of_date is None
            else request.as_of_date
        )

        if resolved_as_of_date is None:
            raise ValueError("No business date is available for portfolio summary queries.")
        portfolio_currency = normalize_currency_code(str(portfolio.base_currency))
        reporting_currency = normalize_currency_code(
            str(request.reporting_currency or portfolio_currency)
        )

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
        row_reporting_values = await self._snapshot_reporting_values(
            rows=rows,
            as_of_date=resolved_as_of_date,
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

        for row, portfolio_value, reporting_value in row_reporting_values:
            snapshot_date = max(snapshot_date, row.snapshot.date)
            total_portfolio += portfolio_value
            total_reporting += reporting_value
            if normalize_control_code(row.snapshot.valuation_status) == UNVALUED_STATUS:
                unvalued_position_count += 1
            else:
                valued_position_count += 1

        return PortfolioSummaryResponse(
            portfolio_id=portfolio.portfolio_id,
            booking_center_code=portfolio.booking_center_code,
            client_id=portfolio.client_id,
            portfolio_currency=portfolio_currency,
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

    async def _snapshot_reporting_values(
        self,
        *,
        rows: list[Any],
        as_of_date: date,
        reporting_currency: str,
    ) -> list[tuple[Any, Decimal, Decimal]]:
        row_native_values = [(row, decimal_or_zero(row.snapshot.market_value)) for row in rows]
        row_reporting_values = []
        for row, native_value in row_native_values:
            row_reporting_values.append(
                await self._convert_amount(
                    amount=native_value,
                    from_currency=row.portfolio.base_currency,
                    to_currency=reporting_currency,
                    as_of_date=as_of_date,
                )
            )
        return [
            (row, native_value, reporting_value)
            for (row, native_value), reporting_value in zip(
                row_native_values,
                row_reporting_values,
                strict=True,
            )
        ]

    async def _resolve_allocation_rows(
        self,
        *,
        rows: list,
        requested_mode: str,
        as_of_date: date,
        reporting_currency: str,
    ) -> tuple[list[tuple[object | None, object, Decimal]], AllocationLookThroughInfo]:
        parent_security_ids, row_parent_security_ids = _allocation_parent_security_ids(rows)
        reporting_values = await self._snapshot_reporting_values(
            rows=rows,
            as_of_date=as_of_date,
            reporting_currency=reporting_currency,
        )
        component_rows = await self.repo.list_instrument_lookthrough_components(
            parent_security_ids=parent_security_ids,
            as_of_date=as_of_date,
        )

        resolved_rows = _resolved_allocation_rows(
            reporting_values=reporting_values,
            row_parent_security_ids=row_parent_security_ids,
        )
        direct_rows = _direct_allocation_rows(resolved_rows)
        components_by_parent = _components_by_parent(component_rows)
        decomposable_parent_ids = self._decomposable_parent_ids(components_by_parent)

        if requested_mode == "direct_only":
            return direct_rows, _direct_only_lookthrough_info(
                requested_mode=requested_mode,
                supported=bool(decomposable_parent_ids),
            )

        (
            allocation_rows,
            decomposed_position_count,
            undecomposed_requested_count,
        ) = self._lookthrough_allocation_rows(
            resolved_rows=resolved_rows,
            components_by_parent=components_by_parent,
            decomposable_parent_ids=decomposable_parent_ids,
        )

        if decomposed_position_count == 0:
            return direct_rows, _unsupported_lookthrough_info(requested_mode=requested_mode)

        return allocation_rows, _applied_lookthrough_info(
            requested_mode=requested_mode,
            decomposed_position_count=decomposed_position_count,
            undecomposed_requested_count=undecomposed_requested_count,
        )

    def _lookthrough_allocation_rows(
        self,
        *,
        resolved_rows: list[ResolvedAllocationRow],
        components_by_parent: dict[str, list[InstrumentLookthroughComponentRow]],
        decomposable_parent_ids: set[str],
    ) -> tuple[list[AllocationOutputRow], int, int]:
        allocation_rows: list[AllocationOutputRow] = []
        decomposed_position_count = 0
        undecomposed_requested_count = 0
        for row, parent_security_id, reporting_value in resolved_rows:
            if parent_security_id not in decomposable_parent_ids:
                allocation_rows.append((row.instrument, row.snapshot, reporting_value))
                undecomposed_requested_count += self._undecomposed_row_count(row)
                continue
            decomposed_position_count += 1
            allocation_rows.extend(
                self._component_allocation_rows(
                    components_by_parent[parent_security_id],
                    reporting_value,
                )
            )
        return allocation_rows, decomposed_position_count, undecomposed_requested_count

    def _undecomposed_row_count(self, row: Any) -> int:
        return 0 if self._cash_balance_resolver.is_cash_row(row) else 1

    @staticmethod
    def _component_allocation_rows(
        components: list[InstrumentLookthroughComponentRow],
        reporting_value: Decimal,
    ) -> list[AllocationOutputRow]:
        return [
            (
                component.component_instrument,
                SimpleNamespace(security_id=component.component_security_id),
                reporting_value * component_weight,
            )
            for component in components
            if (component_weight := ReportingService._component_weight(component)) is not None
        ]

    @staticmethod
    def _decomposable_parent_ids(
        components_by_parent: dict[str, list[InstrumentLookthroughComponentRow]],
    ) -> set[str]:
        return {
            parent_security_id
            for parent_security_id, components in components_by_parent.items()
            if ReportingService._can_decompose_position(components)
        }

    @staticmethod
    def _can_decompose_position(
        components: list[InstrumentLookthroughComponentRow],
    ) -> bool:
        total_weight = _complete_component_weight_total(_component_weights(components))
        if total_weight is None:
            return False
        return abs(total_weight - Decimal("1")) <= Decimal("0.000001")

    @staticmethod
    def _component_weight(component: InstrumentLookthroughComponentRow) -> Decimal | None:
        return decimal_or_none(component.component_weight)

    async def _resolve_scope_portfolios_and_date(
        self,
        scope: ReportingScope,
        requested_as_of_date: date | None,
    ) -> tuple[list, date]:
        if requested_as_of_date is None:
            resolved_as_of_date = await self.repo.get_latest_business_date()
        else:
            resolved_as_of_date = requested_as_of_date

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
            return normalize_currency_code(requested_reporting_currency)
        if scope.scope_type == "portfolio":
            return normalize_currency_code(str(portfolios[0].base_currency))
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
        return await self._fx_converter.convert_amount(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )

    async def _get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        return await self._fx_converter.get_fx_rate(from_currency, to_currency, as_of_date)
