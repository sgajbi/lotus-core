from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.portfolio_allocation import (
    AllocationContributorInput,
    AllocationContributorResult,
    AllocationInputRow,
    calculate_allocation_views,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.strict_decimal import decimal_or_none, decimal_or_zero
from ..dtos.calculation_lineage_dto import CalculationLineageResponse
from ..dtos.reporting_dto import (
    AllocationBucket,
    AllocationContributor,
    AllocationLookThroughInfo,
    AllocationView,
    AssetAllocationQueryRequest,
    AssetAllocationResponse,
    AssetsUnderManagementQueryRequest,
    AssetsUnderManagementResponse,
    AssetsUnderManagementTotals,
    BulkPortfolioSummaryAggregate,
    BulkPortfolioSummaryAggregateTotals,
    BulkPortfolioSummaryItem,
    BulkPortfolioSummaryQueryRequest,
    BulkPortfolioSummaryResponse,
    PortfolioSummaryQueryRequest,
    PortfolioSummaryResponse,
    PortfolioSummarySnapshotMetadata,
    PortfolioSummaryTotals,
    ReportingPortfolioSummary,
    ReportingScope,
    SnapshotCoverageState,
)
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.reporting_repository import (
    InstrumentLookthroughComponentRow,
    ReportingRepository,
    SnapshotPresence,
)
from .cash_balance_service import CashBalanceResolver
from .control_code_normalization import normalize_control_code
from .fx_conversion import CachedFxRateConverter

ZERO = Decimal("0")
USABLE_VALUATION_STATUSES = frozenset({"VALUED", "VALUED_CURRENT", "VALUED_STALE"})
UNVALUED_STATUS = "UNVALUED"
ResolvedAllocationRow = tuple[Any, str | None, Decimal]


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
) -> list[AllocationInputRow]:
    return [
        AllocationInputRow(
            instrument=row.instrument,
            snapshot=row.snapshot,
            market_value_reporting_currency=reporting_value,
            contributor=_direct_allocation_contributor(row, parent_security_id),
        )
        for row, parent_security_id, reporting_value in resolved_rows
    ]


def _required_snapshot_id(snapshot: Any) -> int:
    snapshot_id = int(getattr(snapshot, "id", 0) or 0)
    if snapshot_id < 1:
        raise ValueError("Allocation contributor source snapshot identity is unavailable.")
    return snapshot_id


def _direct_allocation_contributor(
    row: Any,
    parent_security_id: str | None,
) -> AllocationContributorInput:
    if parent_security_id is None:
        raise ValueError("Allocation contributor security identity is unavailable.")
    return AllocationContributorInput(
        contributor_type="direct_position",
        portfolio_id=str(row.portfolio.portfolio_id).strip(),
        security_id=parent_security_id,
        booked_security_id=parent_security_id,
        source_snapshot_id=_required_snapshot_id(row.snapshot),
    )


def _allocation_contributor_dto(result: AllocationContributorResult) -> AllocationContributor:
    source = result.contributor
    return AllocationContributor(
        contributor_type=source.contributor_type,
        portfolio_id=source.portfolio_id,
        security_id=source.security_id,
        booked_security_id=source.booked_security_id,
        source_snapshot_id=source.source_snapshot_id,
        component_record_id=source.component_record_id,
        component_weight=source.component_weight,
        component_effective_from=source.component_effective_from,
        component_effective_to=source.component_effective_to,
        component_source_system=source.component_source_system,
        component_source_record_id=source.component_source_record_id,
        market_value_reporting_currency=result.market_value_reporting_currency,
        bucket_weight=result.bucket_weight,
    )


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
    if any(weight < ZERO or weight > Decimal("1") for weight in complete_weights):
        return None
    return sum(complete_weights, ZERO)


def _cash_balance_totals(cash_account_records: list[Any]) -> tuple[Decimal, Decimal]:
    return (
        sum((record.balance_portfolio_currency for record in cash_account_records), ZERO),
        sum((record.balance_reporting_currency for record in cash_account_records), ZERO),
    )


@dataclass
class _PortfolioSummaryRollup:
    total_portfolio: Decimal = ZERO
    total_reporting: Decimal = ZERO
    valued_position_count: int = 0
    unvalued_position_count: int = 0
    snapshot_date: date | None = None

    def add(self, *, row: Any, portfolio_value: Decimal, reporting_value: Decimal) -> None:
        if self.snapshot_date is None:
            self.snapshot_date = row.snapshot.date
        else:
            self.snapshot_date = max(self.snapshot_date, row.snapshot.date)
        self.total_portfolio += portfolio_value
        self.total_reporting += reporting_value
        if _is_unvalued_snapshot(row):
            self.unvalued_position_count += 1
        else:
            self.valued_position_count += 1


def _is_unvalued_snapshot(row: Any) -> bool:
    return bool(normalize_control_code(row.snapshot.valuation_status) == UNVALUED_STATUS)


def _aum_coverage_state(
    *,
    rows: list[Any],
    presence: SnapshotPresence | None,
    resolved_as_of_date: date,
) -> SnapshotCoverageState:
    """Classify AUM source coverage without treating a numeric zero as missing data."""
    if not rows:
        if presence is None:
            return "NO_SNAPSHOT"
        return "UNAVAILABLE" if presence.expected_open_count > 0 else "LOADED_EMPTY"
    if presence is not None and presence.expected_open_count > len(rows):
        return "UNAVAILABLE"
    if any(row.snapshot.market_value is None for row in rows):
        return "UNAVAILABLE"
    if any(row.snapshot.date < resolved_as_of_date for row in rows):
        return "CARRY_FORWARD"
    if all(decimal_or_zero(row.snapshot.market_value) == ZERO for row in rows):
        return "MEASURED_ZERO"
    return "MEASURED"


def _portfolio_summary_rollup(
    *,
    row_reporting_values: list[tuple[Any, Decimal, Decimal]],
    resolved_as_of_date: date,
) -> _PortfolioSummaryRollup:
    rollup = _PortfolioSummaryRollup(snapshot_date=resolved_as_of_date)
    for row, portfolio_value, reporting_value in row_reporting_values:
        rollup.add(row=row, portfolio_value=portfolio_value, reporting_value=reporting_value)
    return rollup


def _portfolio_summary_totals(
    *,
    total_portfolio: Decimal,
    total_reporting: Decimal,
    cash_portfolio: Decimal,
    cash_reporting: Decimal,
) -> PortfolioSummaryTotals:
    return PortfolioSummaryTotals(
        total_market_value_portfolio_currency=total_portfolio,
        total_market_value_reporting_currency=total_reporting,
        cash_balance_portfolio_currency=cash_portfolio,
        cash_balance_reporting_currency=cash_reporting,
        invested_market_value_portfolio_currency=total_portfolio - cash_portfolio,
        invested_market_value_reporting_currency=total_reporting - cash_reporting,
    )


def _bulk_summary_coverage(
    *,
    rows: list[Any],
    presence: SnapshotPresence | None,
    resolved_as_of_date: date,
) -> tuple[str, str]:
    if presence is None:
        return "NO_SNAPSHOT", "no_source_snapshot"
    if not rows:
        if presence.expected_open_count > 0:
            return "PARTIAL", "open_position_coverage_gap"
        return "LOADED_EMPTY", "source_snapshot_has_no_open_positions"
    if presence.expected_open_count > len(rows):
        return "PARTIAL", "open_position_coverage_gap"
    if any(row.snapshot.market_value is None for row in rows):
        return "PARTIAL", "market_value_missing"
    if any(
        normalize_control_code(row.snapshot.valuation_status) not in USABLE_VALUATION_STATUSES
        for row in rows
    ):
        return "PARTIAL", "valuation_status_not_valued"
    if any(row.instrument is None for row in rows):
        return "PARTIAL", "instrument_classification_missing"
    if any(not _has_usable_cash_classification(row) for row in rows):
        return "PARTIAL", "cash_classification_missing"
    if any(row.snapshot.date < resolved_as_of_date for row in rows):
        return "CARRY_FORWARD", "latest_source_snapshot_precedes_as_of_date"
    if all(decimal_or_zero(row.snapshot.market_value) == ZERO for row in rows):
        return "MEASURED_ZERO", "source_measured_zero"
    return "COMPLETE", "all_source_positions_covered"


def _has_usable_cash_classification(row: Any) -> bool:
    """Require product and asset classification to agree before cash is reported."""
    instrument = row.instrument
    product_type = normalize_control_code(getattr(instrument, "product_type", None))
    asset_class = normalize_control_code(getattr(instrument, "asset_class", None))
    if not product_type and not asset_class:
        return False
    return (product_type == "CASH") == (asset_class == "CASH")


def _portfolio_summary_metadata(
    *,
    rollup: _PortfolioSummaryRollup,
    resolved_as_of_date: date,
    row_count: int,
    cash_account_count: int,
) -> PortfolioSummarySnapshotMetadata:
    return PortfolioSummarySnapshotMetadata(
        snapshot_date=rollup.snapshot_date or resolved_as_of_date,
        position_count=row_count,
        cash_account_count=cash_account_count,
        valued_position_count=rollup.valued_position_count,
        unvalued_position_count=rollup.unvalued_position_count,
    )


def _portfolio_summary_currencies(
    *,
    portfolio: Any,
    requested_reporting_currency: str | None,
) -> tuple[str, str]:
    portfolio_currency = normalize_currency_code(str(portfolio.base_currency))
    reporting_currency = normalize_currency_code(
        str(requested_reporting_currency or portfolio_currency)
    )
    return portfolio_currency, reporting_currency


def _portfolio_summary_response(
    *,
    portfolio: Any,
    portfolio_currency: str,
    reporting_currency: str,
    resolved_as_of_date: date,
    totals: PortfolioSummaryTotals,
    metadata: PortfolioSummarySnapshotMetadata,
) -> PortfolioSummaryResponse:
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
        totals=totals,
        snapshot_metadata=metadata,
    )


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
            include_presence=True,
        )
        raw_snapshot_presence = await self.repo.list_snapshot_presence(
            portfolio_ids=[portfolio.portfolio_id for portfolio in portfolios],
            as_of_date=resolved_as_of_date,
        )
        snapshot_presence = raw_snapshot_presence if isinstance(raw_snapshot_presence, dict) else {}

        per_portfolio_reporting: dict[str, Decimal] = defaultdict(lambda: ZERO)
        per_portfolio_native: dict[str, Decimal] = defaultdict(lambda: ZERO)
        per_portfolio_positions: dict[str, int] = defaultdict(int)
        rows_by_portfolio: dict[str, list[Any]] = defaultdict(list)

        row_reporting_values = await self._snapshot_reporting_values(
            rows=rows,
            as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
        )

        for row, native_value, reporting_value in row_reporting_values:
            portfolio_id = row.portfolio.portfolio_id
            per_portfolio_native[portfolio_id] += native_value
            per_portfolio_reporting[portfolio_id] += reporting_value
            per_portfolio_positions[portfolio_id] += 1
            rows_by_portfolio[portfolio_id].append(row)

        portfolio_summaries: list[ReportingPortfolioSummary] = []
        total_positions = 0
        total_aum_reporting = ZERO
        for portfolio in portfolios:
            portfolio_id = portfolio.portfolio_id
            presence = snapshot_presence.get(portfolio_id)
            portfolio_rows = rows_by_portfolio[portfolio_id]
            total_positions += per_portfolio_positions[portfolio_id]
            total_aum_reporting += per_portfolio_reporting[portfolio_id]
            portfolio_summaries.append(
                ReportingPortfolioSummary(
                    portfolio_id=portfolio_id,
                    booking_center_code=portfolio.booking_center_code,
                    client_id=portfolio.client_id,
                    portfolio_currency=normalize_currency_code(str(portfolio.base_currency)),
                    aum_portfolio_currency=(
                        per_portfolio_native[portfolio_id]
                        if request.scope.scope_type == "portfolio"
                        else None
                    ),
                    aum_reporting_currency=per_portfolio_reporting[portfolio_id],
                    position_count=per_portfolio_positions[portfolio_id],
                    snapshot_found=presence is not None or bool(portfolio_rows),
                    snapshot_date=(
                        presence.snapshot_date
                        if presence is not None
                        else (
                            max(row.snapshot.date for row in portfolio_rows)
                            if portfolio_rows
                            else None
                        )
                    ),
                    coverage_state=_aum_coverage_state(
                        rows=portfolio_rows,
                        presence=presence,
                        resolved_as_of_date=resolved_as_of_date,
                    ),
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
            rows=allocation_rows,
            dimensions=request.dimensions,
            contributor_limit_per_bucket=request.contributor_limit_per_bucket,
            calculation_context={
                "applied_look_through_mode": look_through_info.applied_mode,
                "as_of_date": resolved_as_of_date,
                "reporting_currency": reporting_currency,
                "requested_look_through_mode": request.look_through_mode,
                "scope": request.scope.model_dump(mode="python"),
                "scope_type": request.scope.scope_type,
            },
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
                        contributor_count=bucket.contributor_count,
                        contributors=[
                            _allocation_contributor_dto(contributor)
                            for contributor in bucket.contributors
                        ],
                        contributors_truncated=bucket.contributors_truncated,
                        omitted_market_value_reporting_currency=(
                            bucket.omitted_market_value_reporting_currency
                        ),
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
            calculation_lineage=CalculationLineageResponse(
                **allocation_result.calculation_lineage.lineage_payload()
            ),
            views=views,
        )

    async def get_portfolio_summary(
        self, request: PortfolioSummaryQueryRequest
    ) -> PortfolioSummaryResponse:
        portfolio = await self._get_required_portfolio(request.portfolio_id)
        resolved_as_of_date = await self._resolve_portfolio_summary_date(request.as_of_date)
        portfolio_currency, reporting_currency = _portfolio_summary_currencies(
            portfolio=portfolio,
            requested_reporting_currency=request.reporting_currency,
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

        cash_portfolio, cash_reporting = _cash_balance_totals(cash_account_records)
        rollup = _portfolio_summary_rollup(
            row_reporting_values=row_reporting_values,
            resolved_as_of_date=resolved_as_of_date,
        )
        return _portfolio_summary_response(
            portfolio=portfolio,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            resolved_as_of_date=resolved_as_of_date,
            totals=_portfolio_summary_totals(
                total_portfolio=rollup.total_portfolio,
                total_reporting=rollup.total_reporting,
                cash_portfolio=cash_portfolio,
                cash_reporting=cash_reporting,
            ),
            metadata=_portfolio_summary_metadata(
                rollup=rollup,
                resolved_as_of_date=resolved_as_of_date,
                row_count=len(rows),
                cash_account_count=len(cash_account_records),
            ),
        )

    async def get_bulk_portfolio_summary(
        self, request: BulkPortfolioSummaryQueryRequest
    ) -> BulkPortfolioSummaryResponse:
        """Resolve a bounded cohort from one source snapshot read.

        The caller supplies already-authorized identifiers. Missing members and source/FX
        failures remain explicit result items so a partial cohort can never be mistaken for a
        complete aggregate.
        """
        resolved_as_of_date = await self._resolve_portfolio_summary_date(request.as_of_date)
        portfolios = await self.repo.list_portfolios(portfolio_ids=request.portfolio_ids)
        portfolios_by_id = {str(portfolio.portfolio_id): portfolio for portfolio in portfolios}
        found_ids = [
            portfolio_id
            for portfolio_id in request.portfolio_ids
            if portfolio_id in portfolios_by_id
        ]

        reporting_currency: str | None = None
        if request.reporting_currency:
            reporting_currency = normalize_currency_code(request.reporting_currency)
        elif len(portfolios) == 1:
            reporting_currency = normalize_currency_code(str(portfolios[0].base_currency))

        rows_by_portfolio: dict[str, list[Any]] = defaultdict(list)
        snapshot_presence: dict[str, SnapshotPresence] = {}
        if found_ids:
            rows = await self.repo.list_latest_snapshot_rows(
                portfolio_ids=found_ids,
                as_of_date=resolved_as_of_date,
                include_presence=True,
            )
            raw_presence = await self.repo.list_snapshot_presence(
                portfolio_ids=found_ids,
                as_of_date=resolved_as_of_date,
            )
            snapshot_presence = raw_presence if isinstance(raw_presence, dict) else {}
            for row in rows:
                rows_by_portfolio[str(row.portfolio.portfolio_id)].append(row)

        items: list[BulkPortfolioSummaryItem] = []
        aggregate_total_portfolio = ZERO
        aggregate_total_reporting = ZERO
        aggregate_cash_portfolio = ZERO
        aggregate_cash_reporting = ZERO
        aggregate_invested_portfolio = ZERO
        aggregate_invested_reporting = ZERO
        aggregate_portfolio_currency: str | None = None
        aggregate_native_currency_compatible = True
        fx_failures: set[tuple[str, str, date]] = set()
        aggregate_covered = True
        covered_count = 0
        for portfolio_id in request.portfolio_ids:
            portfolio = portfolios_by_id.get(portfolio_id)
            if portfolio is None:
                aggregate_covered = False
                items.append(
                    BulkPortfolioSummaryItem(
                        portfolio_id=portfolio_id,
                        resolved_as_of_date=resolved_as_of_date,
                        coverage_state="INVALID_PORTFOLIO",
                        coverage_reason="portfolio_not_found",
                        snapshot_row_count=0,
                        expected_open_position_count=0,
                    )
                )
                continue

            portfolio_rows = rows_by_portfolio.get(portfolio_id, [])
            presence = snapshot_presence.get(portfolio_id)
            member, totals = await self._build_bulk_summary_member(
                portfolio=portfolio,
                portfolio_rows=portfolio_rows,
                presence=presence,
                resolved_as_of_date=resolved_as_of_date,
                reporting_currency=reporting_currency,
                fx_failures=fx_failures,
            )
            items.append(member)
            if totals is None:
                aggregate_covered = False
            else:
                covered_count += 1
                aggregate_total_portfolio += totals.total_market_value_portfolio_currency
                aggregate_total_reporting += totals.total_market_value_reporting_currency
                aggregate_cash_portfolio += totals.cash_balance_portfolio_currency
                aggregate_cash_reporting += totals.cash_balance_reporting_currency
                aggregate_invested_portfolio += totals.invested_market_value_portfolio_currency
                aggregate_invested_reporting += totals.invested_market_value_reporting_currency
                member_currency = member.portfolio_currency
                if aggregate_portfolio_currency is None:
                    aggregate_portfolio_currency = member_currency
                elif aggregate_portfolio_currency != member_currency:
                    aggregate_native_currency_compatible = False

        if aggregate_covered and covered_count == len(request.portfolio_ids):
            aggregate = BulkPortfolioSummaryAggregate(
                portfolio_count=len(request.portfolio_ids),
                coverage_state="COMPLETE",
                coverage_reason="all_members_covered",
                totals=BulkPortfolioSummaryAggregateTotals(
                    total_market_value_portfolio_currency=(
                        aggregate_total_portfolio if aggregate_native_currency_compatible else None
                    ),
                    total_market_value_reporting_currency=aggregate_total_reporting,
                    cash_balance_portfolio_currency=(
                        aggregate_cash_portfolio if aggregate_native_currency_compatible else None
                    ),
                    cash_balance_reporting_currency=aggregate_cash_reporting,
                    invested_market_value_portfolio_currency=(
                        aggregate_invested_portfolio
                        if aggregate_native_currency_compatible
                        else None
                    ),
                    invested_market_value_reporting_currency=aggregate_invested_reporting,
                ),
            )
        else:
            aggregate = BulkPortfolioSummaryAggregate(
                portfolio_count=len(request.portfolio_ids),
                coverage_state="PARTIAL" if covered_count else "UNAVAILABLE",
                coverage_reason=(
                    "member_coverage_incomplete"
                    if covered_count
                    else "no_member_has_trustworthy_totals"
                ),
                totals=None,
            )

        return BulkPortfolioSummaryResponse(
            requested_portfolio_ids=request.portfolio_ids,
            resolved_as_of_date=resolved_as_of_date,
            reporting_currency=reporting_currency,
            portfolios=items,
            aggregate=aggregate,
        )

    async def _build_bulk_summary_member(
        self,
        *,
        portfolio: Any,
        portfolio_rows: list[Any],
        presence: SnapshotPresence | None,
        resolved_as_of_date: date,
        reporting_currency: str | None,
        fx_failures: set[tuple[str, str, date]],
    ) -> tuple[BulkPortfolioSummaryItem, PortfolioSummaryTotals | None]:
        portfolio_id = str(portfolio.portfolio_id)
        portfolio_currency = normalize_currency_code(str(portfolio.base_currency))
        effective_reporting_currency = reporting_currency or portfolio_currency
        snapshot_date = (
            presence.snapshot_date
            if presence
            else max((row.snapshot.date for row in portfolio_rows), default=None)
        )
        expected_open_count = presence.expected_open_count if presence else 0
        coverage_state, coverage_reason = _bulk_summary_coverage(
            rows=portfolio_rows,
            presence=presence,
            resolved_as_of_date=resolved_as_of_date,
        )
        totals: PortfolioSummaryTotals | None = None
        if coverage_state in {"COMPLETE", "MEASURED_ZERO", "CARRY_FORWARD"}:
            try:
                row_reporting_values = await self._snapshot_reporting_values(
                    rows=portfolio_rows,
                    as_of_date=resolved_as_of_date,
                    reporting_currency=effective_reporting_currency,
                    fx_failures=fx_failures,
                )
            except ValueError:
                coverage_state = "FX_UNAVAILABLE"
                coverage_reason = "reporting_fx_unavailable"
            else:
                total_portfolio = sum((native for _, native, _ in row_reporting_values), ZERO)
                total_reporting = sum((converted for _, _, converted in row_reporting_values), ZERO)
                cash_values = [
                    (native, converted)
                    for row, native, converted in row_reporting_values
                    if self._cash_balance_resolver.is_cash_row(row)
                ]
                totals = _portfolio_summary_totals(
                    total_portfolio=total_portfolio,
                    total_reporting=total_reporting,
                    cash_portfolio=sum((native for native, _ in cash_values), ZERO),
                    cash_reporting=sum((converted for _, converted in cash_values), ZERO),
                )

        return (
            BulkPortfolioSummaryItem(
                portfolio_id=portfolio_id,
                booking_center_code=portfolio.booking_center_code,
                client_id=portfolio.client_id,
                portfolio_currency=portfolio_currency,
                reporting_currency=effective_reporting_currency,
                resolved_as_of_date=resolved_as_of_date,
                coverage_state=coverage_state,
                coverage_reason=coverage_reason,
                snapshot_date=snapshot_date,
                snapshot_row_count=len(portfolio_rows),
                expected_open_position_count=expected_open_count,
                totals=totals,
            ),
            totals,
        )

    async def _get_required_portfolio(self, portfolio_id: str):
        portfolio = await self.repo.get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            raise LookupError(f"Portfolio with id {portfolio_id} not found")
        return portfolio

    async def _resolve_portfolio_summary_date(self, requested_as_of_date: date | None) -> date:
        resolved_as_of_date = (
            await self.repo.get_latest_business_date()
            if requested_as_of_date is None
            else requested_as_of_date
        )
        if resolved_as_of_date is None:
            raise ValueError("No business date is available for portfolio summary queries.")
        return resolved_as_of_date

    async def _snapshot_reporting_values(
        self,
        *,
        rows: list[Any],
        as_of_date: date,
        reporting_currency: str,
        fx_failures: set[tuple[str, str, date]] | None = None,
    ) -> list[tuple[Any, Decimal, Decimal]]:
        row_native_values = [(row, decimal_or_zero(row.snapshot.market_value)) for row in rows]
        row_reporting_values = []
        for row, native_value in row_native_values:
            from_currency = str(normalize_currency_code(str(row.portfolio.base_currency)))
            to_currency = str(normalize_currency_code(reporting_currency))
            fx_key = (from_currency, to_currency, as_of_date)
            if fx_failures is not None and fx_key in fx_failures:
                raise ValueError(f"FX rate not found for {from_currency}/{to_currency}.")
            try:
                converted = await self._convert_amount(
                    amount=native_value,
                    from_currency=from_currency,
                    to_currency=to_currency,
                    as_of_date=as_of_date,
                )
            except ValueError:
                if fx_failures is not None:
                    fx_failures.add(fx_key)
                raise
            row_reporting_values.append(converted)
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
    ) -> tuple[list[AllocationInputRow], AllocationLookThroughInfo]:
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
    ) -> tuple[list[AllocationInputRow], int, int]:
        allocation_rows: list[AllocationInputRow] = []
        decomposed_position_count = 0
        undecomposed_requested_count = 0
        for row, parent_security_id, reporting_value in resolved_rows:
            if parent_security_id not in decomposable_parent_ids:
                allocation_rows.append(
                    AllocationInputRow(
                        instrument=row.instrument,
                        snapshot=row.snapshot,
                        market_value_reporting_currency=reporting_value,
                        contributor=_direct_allocation_contributor(row, parent_security_id),
                    )
                )
                undecomposed_requested_count += self._undecomposed_row_count(row)
                continue
            decomposed_position_count += 1
            allocation_rows.extend(
                self._component_allocation_rows(
                    components_by_parent[parent_security_id],
                    row,
                    parent_security_id,
                    reporting_value,
                )
            )
        return allocation_rows, decomposed_position_count, undecomposed_requested_count

    def _undecomposed_row_count(self, row: Any) -> int:
        return 0 if self._cash_balance_resolver.is_cash_row(row) else 1

    @staticmethod
    def _component_allocation_rows(
        components: list[InstrumentLookthroughComponentRow],
        row: Any,
        parent_security_id: str,
        reporting_value: Decimal,
    ) -> list[AllocationInputRow]:
        return [
            AllocationInputRow(
                instrument=component.component_instrument,
                snapshot=SimpleNamespace(security_id=component.component_security_id),
                market_value_reporting_currency=reporting_value * component_weight,
                contributor=AllocationContributorInput(
                    contributor_type="look_through_component",
                    portfolio_id=str(row.portfolio.portfolio_id).strip(),
                    security_id=component.component_security_id,
                    booked_security_id=parent_security_id,
                    source_snapshot_id=_required_snapshot_id(row.snapshot),
                    component_record_id=component.component_record_id,
                    component_weight=component_weight,
                    component_effective_from=component.effective_from,
                    component_effective_to=component.effective_to,
                    component_source_system=component.source_system,
                    component_source_record_id=component.source_record_id,
                ),
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
        return cast(Decimal | None, decimal_or_none(component.component_weight))

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
            return str(normalize_currency_code(requested_reporting_currency))
        if scope.scope_type == "portfolio":
            return str(normalize_currency_code(str(portfolios[0].base_currency)))
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
        return cast(
            Decimal,
            await self._fx_converter.convert_amount(
                amount=amount,
                from_currency=from_currency,
                to_currency=to_currency,
                as_of_date=as_of_date,
            ),
        )

    async def _get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        return cast(
            Decimal,
            await self._fx_converter.get_fx_rate(from_currency, to_currency, as_of_date),
        )
