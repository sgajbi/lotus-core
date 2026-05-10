from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


class LiquidityLadderBucket(BaseModel):
    bucket_code: str = Field(
        ...,
        description="Deterministic liquidity bucket code for the returned date range.",
        examples=["T_PLUS_2_TO_7"],
    )
    start_date: date = Field(
        ..., description="Inclusive bucket start date.", examples=["2026-03-29"]
    )
    end_date: date = Field(..., description="Inclusive bucket end date.", examples=["2026-04-03"])
    opening_cash_balance_portfolio_currency: Decimal = Field(
        ...,
        description="Portfolio-currency cash balance available at the as-of date.",
        examples=[250000],
    )
    booked_net_cashflow_portfolio_currency: Decimal = Field(
        ...,
        description="Booked net cashflow within the bucket in portfolio currency.",
        examples=[12500],
    )
    projected_settlement_cashflow_portfolio_currency: Decimal = Field(
        ...,
        description=(
            "Projected settlement-dated external deposit or withdrawal movement within the "
            "bucket in portfolio currency."
        ),
        examples=[-50000],
    )
    net_cashflow_portfolio_currency: Decimal = Field(
        ...,
        description="Booked plus projected cashflow within the bucket in portfolio currency.",
        examples=[-37500],
    )
    cumulative_cash_available_portfolio_currency: Decimal = Field(
        ...,
        description=(
            "Opening cash plus cumulative bucket net cashflows through this bucket, in "
            "portfolio currency."
        ),
        examples=[212500],
    )
    cash_shortfall_portfolio_currency: Decimal = Field(
        ...,
        description=(
            "Positive amount by which cumulative cash availability is below zero after this "
            "bucket. This is evidence, not a funding recommendation."
        ),
        examples=[0],
    )


class AssetLiquidityTierExposure(BaseModel):
    liquidity_tier: str = Field(
        ...,
        description="Source-owned instrument liquidity tier or UNCLASSIFIED when unavailable.",
        examples=["T1"],
    )
    market_value_portfolio_currency: Decimal = Field(
        ...,
        description="Current non-cash market value in portfolio currency for the tier.",
        examples=[850000],
    )
    position_count: int = Field(
        ...,
        description="Number of non-cash positions contributing to the tier.",
        examples=[4],
    )


class PortfolioLiquidityLadderTotals(BaseModel):
    opening_cash_balance_portfolio_currency: Decimal = Field(
        ...,
        description="Total source cash balance at the as-of date in portfolio currency.",
        examples=[250000],
    )
    projected_cash_available_end_portfolio_currency: Decimal = Field(
        ...,
        description="Projected cash available at the end of the returned ladder horizon.",
        examples=[212500],
    )
    maximum_cash_shortfall_portfolio_currency: Decimal = Field(
        ...,
        description="Largest positive cash shortfall observed across returned buckets.",
        examples=[0],
    )
    non_cash_market_value_portfolio_currency: Decimal = Field(
        ...,
        description="Total non-cash market value represented by liquidity-tier exposure.",
        examples=[850000],
    )
    non_cash_position_count: int = Field(
        ...,
        description="Number of non-cash positions represented by liquidity-tier exposure.",
        examples=[4],
    )


class PortfolioLiquidityLadderResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioLiquidityLadder"] = product_name_field(
        "PortfolioLiquidityLadder"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PORT-001"])
    portfolio_currency: str = Field(
        ...,
        description="Portfolio base currency used for all monetary fields.",
        examples=["USD"],
    )
    resolved_as_of_date: date = Field(
        ...,
        description="Business as-of date used to resolve cash and holding state.",
        examples=["2026-03-27"],
    )
    horizon_days: int = Field(
        ...,
        description="Projection horizon in calendar days from the as-of date.",
        examples=[30],
    )
    include_projected: bool = Field(
        ...,
        description="Whether projected settlement-dated external cash movements are included.",
        examples=[True],
    )
    totals: PortfolioLiquidityLadderTotals = Field(
        ..., description="Portfolio-level liquidity ladder totals."
    )
    buckets: list[LiquidityLadderBucket] = Field(
        ..., description="Cash-availability ladder buckets in chronological order."
    )
    asset_liquidity_tiers: list[AssetLiquidityTierExposure] = Field(
        ...,
        description="Current non-cash exposure grouped by source-owned instrument liquidity tier.",
    )
    notes: str = Field(
        ...,
        description="Boundary statement for downstream consumers.",
        examples=[
            (
                "Source liquidity evidence only; not an advice, OMS execution, "
                "or market-impact forecast."
            )
        ],
    )
