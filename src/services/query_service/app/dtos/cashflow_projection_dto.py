from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


class CashflowProjectionPoint(BaseModel):
    projection_date: date = Field(..., description="Projection date.", examples=["2026-03-05"])
    net_cashflow: Decimal = Field(
        ...,
        description="Net portfolio cashflow for the date in portfolio base currency.",
        examples=[-12500.50],
    )
    projected_cumulative_cashflow: Decimal = Field(
        ...,
        description="Running cumulative cashflow across returned projection points.",
        examples=[-31250.75],
    )


class CashflowProjectionResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioCashflowProjection"] = product_name_field(
        "PortfolioCashflowProjection"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    as_of_date: date = Field(
        ...,
        description="Business date anchor used for projection baseline.",
        examples=["2026-03-01"],
    )
    range_start_date: date = Field(
        ..., description="Start date of projection range.", examples=["2026-03-01"]
    )
    range_end_date: date = Field(
        ..., description="End date of projection range.", examples=["2026-03-11"]
    )
    include_projected: bool = Field(
        ...,
        description=(
            "When true, returns future-dated projected flows beyond as_of_date. "
            "When false, returns booked flows only up to as_of_date."
        ),
        examples=[True],
    )
    portfolio_currency: str = Field(
        ...,
        description=(
            "ISO currency code for net_cashflow, projected_cumulative_cashflow, "
            "and total_net_cashflow. Sourced from the portfolio base currency."
        ),
        examples=["USD"],
    )
    points: List[CashflowProjectionPoint] = Field(
        ..., description="Daily projection points in ascending date order."
    )
    total_net_cashflow: Decimal = Field(
        ...,
        description="Total net cashflow across returned projection points.",
        examples=[-48750.25],
    )
    projection_days: int = Field(
        ..., description="Projection window length in days.", examples=[10]
    )
    notes: Optional[str] = Field(
        None,
        description="Additional context for operators or downstream analytics.",
        examples=["Projected window includes settlement-dated future external cash movements."],
    )
