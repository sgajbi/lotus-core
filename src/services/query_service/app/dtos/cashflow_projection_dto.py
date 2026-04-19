from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class CashflowProjectionPoint(BaseModel):
    projection_date: date = Field(
        ..., description="Projection date.", examples=["2026-03-05"]
    )
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


class CashflowProjectionResponse(BaseModel):
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
