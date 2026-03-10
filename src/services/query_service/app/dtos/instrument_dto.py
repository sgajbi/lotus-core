from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InstrumentRecord(BaseModel):
    """
    Represents a single, detailed instrument record for API responses.
    """

    security_id: str = Field(
        ...,
        description="Canonical security identifier.",
        examples=["SEC-US-AAPL"],
    )
    name: str = Field(
        ...,
        description="Instrument display name.",
        examples=["Apple Inc Common Stock"],
    )
    isin: str = Field(
        ...,
        description="International Securities Identification Number.",
        examples=["US0378331005"],
    )
    currency: str = Field(
        ...,
        description="Primary instrument currency.",
        examples=["USD"],
    )
    product_type: str = Field(
        ...,
        description="Canonical product type.",
        examples=["Equity"],
    )
    asset_class: Optional[str] = Field(
        None,
        description="Optional asset-class classification.",
        examples=["Equity"],
    )
    portfolio_id: Optional[str] = Field(
        None,
        description="Optional portfolio identifier when the instrument is portfolio-scoped.",
        examples=["PORT-FX-001"],
    )
    trade_date: Optional[date] = Field(
        None,
        description="Optional trade date associated with the instrument record.",
        examples=["2026-03-10"],
    )
    pair_base_currency: Optional[str] = Field(
        None,
        description="FX pair base currency when the record represents an FX contract instrument.",
        examples=["USD"],
    )
    pair_quote_currency: Optional[str] = Field(
        None,
        description="FX pair quote currency when the record represents an FX contract instrument.",
        examples=["SGD"],
    )
    buy_currency: Optional[str] = Field(
        None,
        description="FX buy leg currency when applicable.",
        examples=["USD"],
    )
    sell_currency: Optional[str] = Field(
        None,
        description="FX sell leg currency when applicable.",
        examples=["SGD"],
    )
    buy_amount: Optional[Decimal] = Field(
        None,
        description="FX buy leg notional amount when applicable.",
        examples=["1000000"],
    )
    sell_amount: Optional[Decimal] = Field(
        None,
        description="FX sell leg notional amount when applicable.",
        examples=["1345000"],
    )
    contract_rate: Optional[Decimal] = Field(
        None,
        description="FX contract rate when applicable.",
        examples=["1.345000"],
    )

    model_config = ConfigDict(from_attributes=True)


class PaginatedInstrumentResponse(BaseModel):
    """
    Represents the paginated API response for an instrument query.
    """

    total: int = Field(..., description="The total number of instruments matching the query.")
    skip: int = Field(..., description="The number of records skipped (offset).")
    limit: int = Field(..., description="The maximum number of records returned.")
    instruments: List[InstrumentRecord] = Field(
        ..., description="The list of instrument records for the current page."
    )
