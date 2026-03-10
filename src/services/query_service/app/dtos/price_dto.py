from datetime import date
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class MarketPriceRecord(BaseModel):
    """
    Represents a single market price record for an API response.
    """

    price_date: date = Field(
        ...,
        description="Business date of the market price observation.",
        examples=["2026-03-10"],
    )
    price: Decimal = Field(
        ...,
        description="Observed market price for the security on the given date.",
        examples=["185.4200"],
    )
    currency: str = Field(
        ...,
        description="Currency of the reported market price.",
        examples=["USD"],
    )

    model_config = ConfigDict(from_attributes=True)


class MarketPriceResponse(BaseModel):
    """
    Represents the API response for a market price query.
    """

    security_id: str = Field(
        ...,
        description="Security identifier for the requested market-price series.",
        examples=["SEC-US-AAPL"],
    )
    prices: List[MarketPriceRecord] = Field(
        ...,
        description="Market price records for the requested security and date range.",
    )
