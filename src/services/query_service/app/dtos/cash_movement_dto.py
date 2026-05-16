from datetime import date
from decimal import Decimal
from typing import List, Literal

from pydantic import BaseModel, Field

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


class CashMovementBucket(BaseModel):
    classification: str = Field(
        ...,
        description="Source-owned cashflow classification for the grouped cash movement rows.",
        examples=["CASHFLOW_OUT"],
    )
    timing: str = Field(
        ...,
        description="Source-owned timing bucket for the grouped cash movement rows.",
        examples=["SETTLED"],
    )
    currency: str = Field(
        ...,
        description="ISO currency code for total_amount.",
        examples=["USD"],
    )
    is_position_flow: bool = Field(
        ...,
        description="True when the grouped rows are position-scoped cash movements.",
        examples=[False],
    )
    is_portfolio_flow: bool = Field(
        ...,
        description="True when the grouped rows are portfolio-level cash movements.",
        examples=[True],
    )
    cashflow_count: int = Field(
        ...,
        description="Number of latest cashflow source rows included in this bucket.",
        examples=[3],
    )
    total_amount: Decimal = Field(
        ...,
        description="Signed total amount for this cash movement bucket in currency.",
        examples=[-15000],
    )
    movement_direction: Literal["INFLOW", "OUTFLOW", "FLAT"] = Field(
        ...,
        description="Direction derived from the sign of total_amount only.",
        examples=["OUTFLOW"],
    )


class PortfolioCashMovementSummaryResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioCashMovementSummary"] = product_name_field(
        "PortfolioCashMovementSummary"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    start_date: date = Field(
        ...,
        description="Inclusive cashflow-date window start.",
        examples=["2026-03-01"],
    )
    end_date: date = Field(
        ...,
        description="Inclusive cashflow-date window end.",
        examples=["2026-03-31"],
    )
    buckets: List[CashMovementBucket] = Field(
        ...,
        description="Cash movement totals grouped by classification, timing, currency, and scope.",
    )
    cashflow_count: int = Field(
        ...,
        description="Total number of latest cashflow source rows included across all buckets.",
        examples=[8],
    )
    notes: str = Field(
        ...,
        description="Boundaries and supportability posture for this cash movement summary.",
        examples=[
            "Summary aggregates latest cashflow rows only; it is not a forecast, funding recommendation, treasury instruction, or OMS acknowledgement."
        ],
    )
