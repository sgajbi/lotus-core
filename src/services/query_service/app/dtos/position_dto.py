# services/query-service/app/dtos/position_dto.py
from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from .valuation_dto import ValuationData


class Position(BaseModel):
    security_id: str = Field(
        ..., description="Security identifier for the position.", examples=["AAPL.OQ"]
    )
    quantity: float = Field(..., description="Position quantity.", examples=[125.0])
    instrument_name: str = Field(
        ..., description="Instrument display name.", examples=["Apple Inc."]
    )
    position_date: date = Field(
        ..., description="Business date of the position snapshot.", examples=["2025-12-30"]
    )
    asset_class: Optional[str] = Field(
        None, description="Asset class for grouping and reporting.", examples=["Equity"]
    )
    isin: Optional[str] = Field(
        None, description="ISIN instrument identifier.", examples=["US0378331005"]
    )
    currency: Optional[str] = Field(
        None, description="Instrument trading currency (ISO 4217).", examples=["USD"]
    )
    sector: Optional[str] = Field(
        None, description="Instrument sector classification.", examples=["Technology"]
    )
    country_of_risk: Optional[str] = Field(
        None,
        description="Instrument country-of-risk classification.",
        examples=["United States"],
    )
    product_type: Optional[str] = Field(
        None,
        description="Instrument product-type classification.",
        examples=["ETF"],
    )
    rating: Optional[str] = Field(
        None,
        description="Credit rating used for reporting and analytics.",
        examples=["AA+"],
    )
    liquidity_tier: Optional[str] = Field(
        None,
        description="Liquidity tier used by advisory suitability and concentration workflows.",
        examples=["L1", "L5"],
    )
    cost_basis: Decimal = Field(
        ..., description="Cost basis in portfolio base currency.", examples=[15000.0]
    )
    cost_basis_local: Optional[Decimal] = Field(
        None, description="Cost basis in local instrument currency.", examples=[15000.0]
    )
    valuation: Optional[ValuationData] = Field(
        None, description="Valuation details for the position snapshot."
    )
    reprocessing_status: Optional[str] = Field(
        None,
        description="Reprocessing status for this portfolio-security key.",
        examples=["CURRENT", "REPROCESSING"],
    )
    held_since_date: Optional[date] = Field(
        None,
        description="Start date of the current continuous holding period in the active epoch.",
        examples=["2025-01-15"],
    )
    weight: Optional[Decimal] = Field(
        None,
        description="Position weight versus total portfolio market value (0.0 to 1.0).",
        examples=[0.2417],
    )

    model_config = ConfigDict(from_attributes=True)


class PortfolioPositionsResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["HoldingsAsOf"] = product_name_field("HoldingsAsOf")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    positions: List[Position] = Field(..., description="Latest positions for the portfolio.")


class PositionHistoryRecord(BaseModel):
    """
    Represents a snapshot of a security's position at a specific point in time,
    as a result of a transaction.
    """

    position_date: date = Field(
        ...,
        description="Business date of this position-history snapshot.",
        examples=["2025-12-30"],
    )
    transaction_id: str = Field(
        ...,
        description="Transaction identifier that produced this position-history state.",
        examples=["TXN-2025-12030-0007"],
    )
    quantity: float = Field(
        ...,
        description="Quantity held as of this position-history record.",
        examples=[125.0],
    )

    cost_basis: Decimal = Field(
        ...,
        description="Total cost basis of the holding as of this position-history record.",
        examples=[15000.0],
    )

    cost_basis_local: Optional[Decimal] = Field(
        None,
        description="Total cost basis in the instrument's local currency.",
        examples=[15000.0],
    )

    valuation: Optional[ValuationData] = Field(
        None, description="Valuation details for this record."
    )
    reprocessing_status: Optional[str] = Field(
        None,
        description="Reprocessing status for this portfolio-security key.",
        examples=["CURRENT", "REPROCESSING"],
    )

    model_config = ConfigDict(from_attributes=True)


class PortfolioPositionHistoryResponse(BaseModel):
    """
    Represents the API response for a portfolio's position history.
    """

    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    security_id: str = Field(
        ...,
        description="Security identifier for which the history is returned.",
        examples=["AAPL.OQ"],
    )
    positions: List[PositionHistoryRecord] = Field(
        ..., description="Time-series list of position-history records for the security."
    )
