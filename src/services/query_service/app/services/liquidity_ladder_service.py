from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.liquidity_ladder_dto import (
    AssetLiquidityTierExposure,
    LiquidityLadderBucket,
    PortfolioLiquidityLadderResponse,
    PortfolioLiquidityLadderTotals,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.cashflow_repository import CashflowRepository
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.reporting_repository import ReportingRepository, ReportingSnapshotRow
from .control_code_normalization import normalize_control_code
from .decimal_amounts import decimal_or_zero
from .snapshot_evidence import latest_snapshot_evidence_timestamp

ZERO = Decimal("0")
CASH_ASSET_CLASS = "CASH"
DEFAULT_HORIZON_DAYS = 30
MAX_HORIZON_DAYS = 366
LIQUIDITY_LADDER_BOUNDARY_NOTE = (
    "Source liquidity evidence only; not an advice, OMS execution, funding recommendation, "
    "best-execution, tax, or market-impact forecast."
)


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
        as_of_date: date | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        include_projected: bool = True,
    ) -> PortfolioLiquidityLadderResponse:
        if horizon_days < 0 or horizon_days > MAX_HORIZON_DAYS:
            raise ValueError(f"horizon_days must be between 0 and {MAX_HORIZON_DAYS}.")

        portfolio = await self.reporting_repo.get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

        resolved_as_of_date = as_of_date or await self.reporting_repo.get_latest_business_date()
        if resolved_as_of_date is None:
            raise ValueError("No business date is available for liquidity ladder queries.")

        rows = await self.reporting_repo.list_latest_snapshot_rows(
            portfolio_ids=[portfolio.portfolio_id],
            as_of_date=resolved_as_of_date,
        )
        cash_rows, non_cash_rows = self._partition_cash_rows(rows)
        opening_cash_balance = self._sum_market_value(cash_rows)
        tier_exposures = self._build_asset_liquidity_tier_exposures(non_cash_rows)

        range_end_date = resolved_as_of_date + timedelta(days=horizon_days)
        booked_series = await self.cashflow_repo.get_portfolio_cashflow_series(
            portfolio_id=portfolio.portfolio_id,
            start_date=resolved_as_of_date,
            end_date=range_end_date,
        )
        projected_series = (
            await self.cashflow_repo.get_projected_settlement_cashflow_series(
                portfolio_id=portfolio.portfolio_id,
                start_date=resolved_as_of_date,
                end_date=range_end_date,
            )
            if include_projected
            else []
        )
        latest_cashflow_evidence = await self.cashflow_repo.get_latest_cashflow_evidence_timestamp(
            portfolio_id=portfolio.portfolio_id,
            start_date=resolved_as_of_date,
            end_date=range_end_date,
            include_projected=include_projected,
        )

        buckets = self._build_ladder_buckets(
            as_of_date=resolved_as_of_date,
            horizon_days=horizon_days,
            opening_cash_balance=opening_cash_balance,
            booked_series=dict(booked_series),
            projected_series=dict(projected_series),
        )
        totals = self._build_totals(
            opening_cash_balance=opening_cash_balance,
            buckets=buckets,
            tier_exposures=tier_exposures,
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
                data_quality_status=self._data_quality_status(rows=rows, buckets=buckets),
                latest_evidence_timestamp=max(
                    (item for item in (latest_snapshot_evidence, latest_cashflow_evidence) if item),
                    default=None,
                ),
                source_batch_fingerprint=(
                    f"liquidity_ladder:{portfolio.portfolio_id}:{resolved_as_of_date}:"
                    f"{range_end_date}:include_projected={str(include_projected).lower()}"
                ),
            ),
        )

    @staticmethod
    def _build_ladder_buckets(
        *,
        as_of_date: date,
        horizon_days: int,
        opening_cash_balance: Decimal,
        booked_series: dict[date, Decimal],
        projected_series: dict[date, Decimal],
    ) -> list[LiquidityLadderBucket]:
        cumulative_cash = opening_cash_balance
        buckets: list[LiquidityLadderBucket] = []
        for date_bucket in _date_buckets(as_of_date=as_of_date, horizon_days=horizon_days):
            booked_cashflow = _sum_series(booked_series, date_bucket)
            projected_cashflow = _sum_series(projected_series, date_bucket)
            net_cashflow = booked_cashflow + projected_cashflow
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
                    cash_shortfall_portfolio_currency=abs(min(cumulative_cash, ZERO)),
                )
            )
        return buckets

    @staticmethod
    def _build_asset_liquidity_tier_exposures(
        rows: list[ReportingSnapshotRow],
    ) -> list[AssetLiquidityTierExposure]:
        tier_values: dict[str, Decimal] = defaultdict(Decimal)
        tier_counts: dict[str, int] = defaultdict(int)
        for row in rows:
            tier = normalize_control_code(
                getattr(row.instrument, "liquidity_tier", None),
                default="UNCLASSIFIED",
            )
            tier_values[tier] += decimal_or_zero(getattr(row.snapshot, "market_value", ZERO))
            tier_counts[tier] += 1
        return [
            AssetLiquidityTierExposure(
                liquidity_tier=tier,
                market_value_portfolio_currency=tier_values[tier],
                position_count=tier_counts[tier],
            )
            for tier in sorted(tier_values)
        ]

    @staticmethod
    def _build_totals(
        *,
        opening_cash_balance: Decimal,
        buckets: list[LiquidityLadderBucket],
        tier_exposures: list[AssetLiquidityTierExposure],
    ) -> PortfolioLiquidityLadderTotals:
        return PortfolioLiquidityLadderTotals(
            opening_cash_balance_portfolio_currency=opening_cash_balance,
            projected_cash_available_end_portfolio_currency=(
                buckets[-1].cumulative_cash_available_portfolio_currency
                if buckets
                else opening_cash_balance
            ),
            maximum_cash_shortfall_portfolio_currency=max(
                (bucket.cash_shortfall_portfolio_currency for bucket in buckets),
                default=ZERO,
            ),
            non_cash_market_value_portfolio_currency=sum(
                (item.market_value_portfolio_currency for item in tier_exposures),
                ZERO,
            ),
            non_cash_position_count=sum(item.position_count for item in tier_exposures),
        )

    @staticmethod
    def _sum_market_value(rows: list[ReportingSnapshotRow]) -> Decimal:
        return sum((decimal_or_zero(row.snapshot.market_value) for row in rows), ZERO)

    @classmethod
    def _partition_cash_rows(
        cls,
        rows: list[ReportingSnapshotRow],
    ) -> tuple[list[ReportingSnapshotRow], list[ReportingSnapshotRow]]:
        cash_rows: list[ReportingSnapshotRow] = []
        non_cash_rows: list[ReportingSnapshotRow] = []
        for row in rows:
            if cls._is_cash_row(row):
                cash_rows.append(row)
            else:
                non_cash_rows.append(row)
        return cash_rows, non_cash_rows

    @staticmethod
    def _is_cash_row(row: ReportingSnapshotRow) -> bool:
        return (
            row.instrument is not None
            and normalize_control_code(getattr(row.instrument, "asset_class", None), default="")
            == CASH_ASSET_CLASS
        )

    @staticmethod
    def _data_quality_status(
        *, rows: list[ReportingSnapshotRow], buckets: list[LiquidityLadderBucket]
    ) -> str:
        if not rows:
            return UNKNOWN
        if not buckets:
            return PARTIAL
        return COMPLETE


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
