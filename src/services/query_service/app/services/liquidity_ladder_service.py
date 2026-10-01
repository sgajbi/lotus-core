from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN
from portfolio_common.source_data_product_metadata import (
    SourceDataDegradationDetail,
    SourceDataDegradationSummary,
    source_data_product_runtime_metadata,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.strict_decimal import decimal_or_zero
from ..dtos.liquidity_ladder_dto import (
    AssetLiquidityTierExposure,
    LiquidityLadderBucket,
    PortfolioLiquidityLadderResponse,
    PortfolioLiquidityLadderTotals,
)
from ..repositories.cashflow_repository import CashflowRepository
from ..repositories.reporting_repository import ReportingRepository, ReportingSnapshotRow
from .cashflow_evidence_window import read_cashflow_evidence_window
from .control_code_normalization import normalize_control_code
from .snapshot_evidence import latest_snapshot_evidence_timestamp
from .valuation_status import has_usable_valuation_status

ZERO = Decimal("0")
CASH_ASSET_CLASS = "CASH"
DEFAULT_HORIZON_DAYS = 30
MAX_HORIZON_DAYS = 366
LIQUIDITY_LADDER_BOUNDARY_NOTE = (
    "Source liquidity evidence only; not an advice, OMS execution, funding recommendation, "
    "best-execution, tax, or market-impact forecast."
)
SOURCE_HOLDINGS_UNAVAILABLE = "SOURCE_HOLDINGS_UNAVAILABLE"
CASH_VALUATION_UNAVAILABLE = "CASH_VALUATION_UNAVAILABLE"
NON_CASH_VALUATION_UNAVAILABLE = "NON_CASH_VALUATION_UNAVAILABLE"
INSTRUMENT_CLASSIFICATION_UNAVAILABLE = "INSTRUMENT_CLASSIFICATION_UNAVAILABLE"


@dataclass(frozen=True)
class LadderDateBucket:
    bucket_code: str
    start_date: date
    end_date: date


class PortfolioLiquidityLadderService:
    def __init__(self, db: AsyncSession):
        self.reporting_repo = ReportingRepository(db)
        self.cashflow_repo = CashflowRepository(db)

    async def get_liquidity_ladder(
        self,
        *,
        portfolio_id: str,
        tenant_context: TenantContext,
        as_of_date: date | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        include_projected: bool = True,
    ) -> PortfolioLiquidityLadderResponse:
        if horizon_days < 0 or horizon_days > MAX_HORIZON_DAYS:
            raise ValueError(f"horizon_days must be between 0 and {MAX_HORIZON_DAYS}.")

        portfolio = await self.reporting_repo.get_portfolio_by_id(
            portfolio_id, tenant_id=tenant_context.tenant_id
        )
        if portfolio is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")
        resolved_as_of_date = (
            await self.reporting_repo.get_latest_business_date()
            if as_of_date is None
            else as_of_date
        )

        if resolved_as_of_date is None:
            raise ValueError("No business date is available for liquidity ladder queries.")

        range_end_date = resolved_as_of_date + timedelta(days=horizon_days)
        rows = await self.reporting_repo.list_latest_snapshot_rows(
            portfolio_ids=[portfolio.portfolio_id],
            as_of_date=resolved_as_of_date,
        )
        cashflow_evidence = await read_cashflow_evidence_window(
            repo=self.cashflow_repo,
            portfolio_id=portfolio.portfolio_id,
            start_date=resolved_as_of_date,
            end_date=range_end_date,
            include_projected=include_projected,
            tenant_id=tenant_context.tenant_id,
        )

        cash_rows, non_cash_rows, unclassified_rows = self._partition_snapshot_rows(rows)
        opening_cash_balance = self._opening_cash_balance(
            rows=rows,
            cash_rows=cash_rows,
            unclassified_rows=unclassified_rows,
        )
        tier_exposures = self._build_asset_liquidity_tier_exposures(non_cash_rows)
        degradation = self._degradation_summary(
            rows=rows,
            cash_rows=cash_rows,
            non_cash_rows=non_cash_rows,
            unclassified_rows=unclassified_rows,
            as_of_date=resolved_as_of_date,
        )

        buckets = self._build_ladder_buckets(
            as_of_date=resolved_as_of_date,
            horizon_days=horizon_days,
            opening_cash_balance=opening_cash_balance,
            booked_series=dict(cashflow_evidence.booked_rows),
            projected_series=dict(cashflow_evidence.projected_rows),
        )
        totals = self._build_totals(
            opening_cash_balance=opening_cash_balance,
            buckets=buckets,
            tier_exposures=tier_exposures,
            rows=rows,
            unclassified_rows=unclassified_rows,
        )
        latest_snapshot_evidence = latest_snapshot_evidence_timestamp(rows)

        return PortfolioLiquidityLadderResponse(
            portfolio_id=portfolio.portfolio_id,
            portfolio_currency=normalize_currency_code(str(portfolio.base_currency)),
            resolved_as_of_date=resolved_as_of_date,
            horizon_days=horizon_days,
            include_projected=include_projected,
            totals=totals,
            buckets=buckets,
            asset_liquidity_tiers=tier_exposures,
            notes=LIQUIDITY_LADDER_BOUNDARY_NOTE,
            **source_data_product_runtime_metadata(
                as_of_date=resolved_as_of_date,
                data_quality_status=self._data_quality_status(
                    rows=rows,
                    buckets=buckets,
                    degradation=degradation,
                ),
                latest_evidence_timestamp=max(
                    (
                        item
                        for item in (
                            latest_snapshot_evidence,
                            cashflow_evidence.latest_evidence_timestamp,
                        )
                        if item
                    ),
                    default=None,
                ),
            ),
            degradation=degradation,
        )

    @staticmethod
    def _build_ladder_buckets(
        *,
        as_of_date: date,
        horizon_days: int,
        opening_cash_balance: Decimal | None,
        booked_series: dict[date, Decimal],
        projected_series: dict[date, Decimal],
    ) -> list[LiquidityLadderBucket]:
        cumulative_cash = opening_cash_balance
        buckets: list[LiquidityLadderBucket] = []
        for date_bucket in _date_buckets(as_of_date=as_of_date, horizon_days=horizon_days):
            booked_cashflow = _sum_series(booked_series, date_bucket)
            projected_cashflow = _sum_series(projected_series, date_bucket)
            net_cashflow = booked_cashflow + projected_cashflow
            if cumulative_cash is not None:
                cumulative_cash += net_cashflow
            buckets.append(
                LiquidityLadderBucket(
                    bucket_code=date_bucket.bucket_code,
                    start_date=date_bucket.start_date,
                    end_date=date_bucket.end_date,
                    opening_cash_balance_portfolio_currency=opening_cash_balance,
                    booked_net_cashflow_portfolio_currency=booked_cashflow,
                    projected_settlement_cashflow_portfolio_currency=projected_cashflow,
                    net_cashflow_portfolio_currency=net_cashflow,
                    cumulative_cash_available_portfolio_currency=cumulative_cash,
                    cash_shortfall_portfolio_currency=(
                        abs(min(cumulative_cash, ZERO)) if cumulative_cash is not None else None
                    ),
                )
            )
        return buckets

    @staticmethod
    def _build_asset_liquidity_tier_exposures(
        rows: list[ReportingSnapshotRow],
    ) -> list[AssetLiquidityTierExposure]:
        tier_values: dict[str, Decimal] = defaultdict(Decimal)
        unavailable_tiers: set[str] = set()
        tier_counts: dict[str, int] = defaultdict(int)
        for row in rows:
            tier = normalize_control_code(
                getattr(row.instrument, "liquidity_tier", None),
                default="UNCLASSIFIED",
            )
            market_value = getattr(row.snapshot, "market_value", None)
            tier_values[tier] += ZERO
            if market_value is None or not _has_usable_snapshot_valuation(row):
                unavailable_tiers.add(tier)
            else:
                tier_values[tier] += Decimal(str(market_value))
            tier_counts[tier] += 1
        return [
            AssetLiquidityTierExposure(
                liquidity_tier=tier,
                market_value_portfolio_currency=(
                    None if tier in unavailable_tiers else tier_values[tier]
                ),
                position_count=tier_counts[tier],
            )
            for tier in sorted(tier_values)
        ]

    @staticmethod
    def _build_totals(
        *,
        opening_cash_balance: Decimal | None,
        buckets: list[LiquidityLadderBucket],
        tier_exposures: list[AssetLiquidityTierExposure],
        rows: list[ReportingSnapshotRow],
        unclassified_rows: list[ReportingSnapshotRow],
    ) -> PortfolioLiquidityLadderTotals:
        non_cash_values = [item.market_value_portfolio_currency for item in tier_exposures]
        non_cash_total_available = (
            bool(rows)
            and not unclassified_rows
            and all(value is not None for value in non_cash_values)
        )
        return PortfolioLiquidityLadderTotals(
            opening_cash_balance_portfolio_currency=opening_cash_balance,
            projected_cash_available_end_portfolio_currency=(
                buckets[-1].cumulative_cash_available_portfolio_currency
                if buckets
                else opening_cash_balance
            ),
            maximum_cash_shortfall_portfolio_currency=max(
                (
                    bucket.cash_shortfall_portfolio_currency
                    for bucket in buckets
                    if bucket.cash_shortfall_portfolio_currency is not None
                ),
                default=None,
            ),
            non_cash_market_value_portfolio_currency=(
                sum((value for value in non_cash_values if value is not None), ZERO)
                if non_cash_total_available
                else None
            ),
            non_cash_position_count=(
                sum(item.position_count for item in tier_exposures)
                if rows and not unclassified_rows
                else None
            ),
        )

    @staticmethod
    def _opening_cash_balance(
        *,
        rows: list[ReportingSnapshotRow],
        cash_rows: list[ReportingSnapshotRow],
        unclassified_rows: list[ReportingSnapshotRow],
    ) -> Decimal | None:
        if (
            not rows
            or unclassified_rows
            or any(
                row.snapshot.market_value is None or not _has_usable_snapshot_valuation(row)
                for row in cash_rows
            )
        ):
            return None
        return sum((Decimal(str(row.snapshot.market_value)) for row in cash_rows), ZERO)

    @staticmethod
    def _partition_snapshot_rows(
        rows: list[ReportingSnapshotRow],
    ) -> tuple[
        list[ReportingSnapshotRow],
        list[ReportingSnapshotRow],
        list[ReportingSnapshotRow],
    ]:
        cash_rows: list[ReportingSnapshotRow] = []
        non_cash_rows: list[ReportingSnapshotRow] = []
        unclassified_rows: list[ReportingSnapshotRow] = []
        for row in rows:
            asset_class = normalize_control_code(
                getattr(row.instrument, "asset_class", None),
                default="",
            )
            if not asset_class:
                unclassified_rows.append(row)
            elif asset_class == CASH_ASSET_CLASS:
                cash_rows.append(row)
            else:
                non_cash_rows.append(row)
        return cash_rows, non_cash_rows, unclassified_rows

    @staticmethod
    def _data_quality_status(
        *,
        rows: list[ReportingSnapshotRow],
        buckets: list[LiquidityLadderBucket],
        degradation: SourceDataDegradationSummary,
    ) -> str:
        if not rows:
            return str(UNKNOWN)
        if not buckets or degradation.status != "NONE":
            return str(PARTIAL)
        return str(COMPLETE)

    @staticmethod
    def _degradation_summary(
        *,
        rows: list[ReportingSnapshotRow],
        cash_rows: list[ReportingSnapshotRow],
        non_cash_rows: list[ReportingSnapshotRow],
        unclassified_rows: list[ReportingSnapshotRow],
        as_of_date: date,
    ) -> SourceDataDegradationSummary:
        details: list[SourceDataDegradationDetail] = []
        if not rows:
            details.append(
                _degradation_detail(
                    section="holdings",
                    affected_fields=_all_qualified_fields(),
                    reason_code=SOURCE_HOLDINGS_UNAVAILABLE,
                    source_as_of_date=as_of_date,
                )
            )
        for row in cash_rows:
            if row.snapshot.market_value is None or not _has_usable_snapshot_valuation(row):
                details.append(
                    _row_degradation_detail(
                        row=row,
                        section="cash",
                        affected_fields=_cash_qualified_fields(),
                        reason_code=CASH_VALUATION_UNAVAILABLE,
                    )
                )
        for row in non_cash_rows:
            if row.snapshot.market_value is None or not _has_usable_snapshot_valuation(row):
                details.append(
                    _row_degradation_detail(
                        row=row,
                        section="asset_liquidity_tiers",
                        affected_fields=[
                            "asset_liquidity_tiers[].market_value_portfolio_currency",
                            "totals.non_cash_market_value_portfolio_currency",
                        ],
                        reason_code=NON_CASH_VALUATION_UNAVAILABLE,
                    )
                )
        for row in unclassified_rows:
            details.append(
                _row_degradation_detail(
                    row=row,
                    section="holdings",
                    affected_fields=_all_qualified_fields(),
                    reason_code=INSTRUMENT_CLASSIFICATION_UNAVAILABLE,
                )
            )
        return SourceDataDegradationSummary(
            status=("UNAVAILABLE" if not rows else "PARTIAL") if details else "NONE",
            reason_codes=sorted({detail.reason_code for detail in details}),
            details=details,
        )


def _degradation_detail(
    *,
    section: str,
    affected_fields: list[str],
    reason_code: str,
    source_as_of_date: date | None,
    record_key: str | None = None,
    latest_evidence_timestamp: datetime | None = None,
) -> SourceDataDegradationDetail:
    return SourceDataDegradationDetail(
        section=section,
        record_key=record_key,
        affected_fields=affected_fields,
        source_kind="UNAVAILABLE",
        source_product_name="HoldingsAsOf",
        source_product_version="v1",
        source_as_of_date=source_as_of_date,
        latest_evidence_timestamp=latest_evidence_timestamp,
        freshness_status="UNAVAILABLE",
        reason_code=reason_code,
    )


def _row_record_key(row: ReportingSnapshotRow) -> str:
    return f"security_id:{str(row.snapshot.security_id).strip()}"


def _row_degradation_detail(
    *,
    row: ReportingSnapshotRow,
    section: str,
    affected_fields: list[str],
    reason_code: str,
) -> SourceDataDegradationDetail:
    return _degradation_detail(
        section=section,
        record_key=_row_record_key(row),
        affected_fields=affected_fields,
        reason_code=reason_code,
        source_as_of_date=getattr(row.snapshot, "date", None),
        latest_evidence_timestamp=latest_snapshot_evidence_timestamp([row]),
    )


def _has_usable_snapshot_valuation(row: ReportingSnapshotRow) -> bool:
    return has_usable_valuation_status(getattr(row.snapshot, "valuation_status", None))


def _cash_qualified_fields() -> list[str]:
    return [
        "totals.opening_cash_balance_portfolio_currency",
        "totals.projected_cash_available_end_portfolio_currency",
        "totals.maximum_cash_shortfall_portfolio_currency",
        "buckets[].opening_cash_balance_portfolio_currency",
        "buckets[].cumulative_cash_available_portfolio_currency",
        "buckets[].cash_shortfall_portfolio_currency",
    ]


def _all_qualified_fields() -> list[str]:
    return [
        *_cash_qualified_fields(),
        "totals.non_cash_market_value_portfolio_currency",
        "totals.non_cash_position_count",
        "asset_liquidity_tiers",
    ]


def _date_buckets(*, as_of_date: date, horizon_days: int) -> list[LadderDateBucket]:
    horizon_end = as_of_date + timedelta(days=horizon_days)
    candidates = [
        ("T0", 0, 0),
        ("T_PLUS_1", 1, 1),
        ("T_PLUS_2_TO_7", 2, 7),
        ("T_PLUS_8_TO_30", 8, 30),
        ("T_PLUS_31_TO_HORIZON", 31, horizon_days),
    ]
    buckets = []
    for bucket_code, start_offset, end_offset in candidates:
        if start_offset > horizon_days:
            continue
        start_date = as_of_date + timedelta(days=start_offset)
        end_date = min(as_of_date + timedelta(days=end_offset), horizon_end)
        if start_date <= end_date:
            buckets.append(
                LadderDateBucket(
                    bucket_code=bucket_code,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
    return buckets


def _sum_series(series: dict[date, Decimal], bucket: LadderDateBucket) -> Decimal:
    return sum(
        (
            decimal_or_zero(amount)
            for flow_date, amount in series.items()
            if bucket.start_date <= flow_date <= bucket.end_date
        ),
        ZERO,
    )
