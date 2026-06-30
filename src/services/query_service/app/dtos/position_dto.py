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
    maturity_date: Optional[date] = Field(
        None,
        description=(
            "Source-owned instrument maturity date for maturity-bearing holdings, when Core "
            "reference data carries the lifecycle date."
        ),
        examples=["2026-07-15"],
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
    positions: List[Position] = Field(
        ...,
        description=(
            "Governed holdings rows for the resolved HoldingsAsOf scope. Rows reflect booked or "
            "projected state according to the request parameters."
        ),
    )


class PortfolioMaturitySummaryResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioMaturitySummary"] = product_name_field(
        "PortfolioMaturitySummary"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier.", examples=["PF-001"])
    source_product_name: Literal["HoldingsAsOf"] = Field(
        "HoldingsAsOf",
        description="Core source-data product used to derive this maturity summary.",
        examples=["HoldingsAsOf"],
    )
    source_product_version: Literal["v1"] = Field(
        "v1",
        description="Version of the source-data product used to derive this maturity summary.",
        examples=["v1"],
    )
    window_start_date: date = Field(
        ...,
        description="Inclusive start date for the maturity summary window.",
        examples=["2026-03-10"],
    )
    window_end_date: date = Field(
        ...,
        description="Inclusive end date for the maturity summary window.",
        examples=["2026-06-08"],
    )
    horizon_days: int = Field(
        ...,
        description="Calendar-day maturity horizon used to derive window_end_date.",
        examples=[90],
        ge=1,
    )
    include_projected: bool = Field(
        False,
        description="Whether projected holdings were included in the underlying HoldingsAsOf read.",
        examples=[False],
    )
    maturity_basis: Literal["CONTRACTUAL_INSTRUMENT_MATURITY_DATE"] = Field(
        "CONTRACTUAL_INSTRUMENT_MATURITY_DATE",
        description=(
            "Lifecycle basis used by this summary. The current implementation uses Core "
            "instrument reference maturity_date facts and does not infer callable, putable, "
            "amortizing, structured-note, lockup, or other product-specific schedules."
        ),
        examples=["CONTRACTUAL_INSTRUMENT_MATURITY_DATE"],
    )
    freshness_status: Literal["CURRENT", "STALE", "UNKNOWN"] = Field(
        ...,
        description="Freshness posture inherited from the underlying HoldingsAsOf evidence.",
        examples=["CURRENT"],
    )
    next_maturity_date: Optional[date] = Field(
        None,
        description=(
            "Earliest source-owned instrument maturity date inside the requested window, or null "
            "when no returned holding matures in the window."
        ),
        examples=["2026-07-15"],
    )
    maturing_holding_count: int = Field(
        ...,
        description="Count of returned holdings with a maturity_date inside the requested window.",
        examples=[3],
        ge=0,
    )
    maturity_bearing_holding_count: int = Field(
        ...,
        description=(
            "Count of returned holdings that Core classifies as maturity-bearing from asset-class "
            "or product-type evidence."
        ),
        examples=[12],
        ge=0,
    )
    missing_maturity_date_count: int = Field(
        ...,
        description=(
            "Count of maturity-bearing holdings where Core reference data does not carry a "
            "maturity_date lifecycle fact."
        ),
        examples=[1],
        ge=0,
    )
    unsupported_maturity_feature_count: int = Field(
        ...,
        description=(
            "Count of returned holdings whose product classification suggests lifecycle features "
            "such as callable, putable, amortizing, structured, lockup, or expiry behavior that "
            "the current contractual-date summary does not fully certify."
        ),
        examples=[0],
        ge=0,
    )
    supportability_status: Literal["SUPPORTED", "PARTIAL", "STALE", "UNAVAILABLE"] = Field(
        ...,
        description=(
            "Summary supportability status after applying HoldingsAsOf data quality, missing "
            "maturity facts, and unsupported lifecycle feature diagnostics."
        ),
        examples=["SUPPORTED"],
    )
    supportability_reasons: list[str] = Field(
        default_factory=list,
        description=(
            "Bounded reason codes explaining partial, stale, or unavailable maturity summary "
            "posture. Empty means the returned summary is supported for contractual maturity-date "
            "use."
        ),
        examples=[["MISSING_INSTRUMENT_MATURITY_DATE"]],
    )
    request_fingerprint: str = Field(
        ...,
        description=(
            "Deterministic fingerprint of the requested portfolio, as-of scope, horizon, "
            "projection mode, and resulting summary content. This is request/product lineage, not "
            "an upstream source-batch fingerprint."
        ),
        examples=["maturity_summary:3a4f5b6c7d8e9f01"],
    )


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
