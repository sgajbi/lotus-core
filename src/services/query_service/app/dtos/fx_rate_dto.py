from datetime import date
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class FxRateRecord(BaseModel):
    """
    Represents a single FX rate record for an API response.
    """

    rate_date: date = Field(
        ...,
        description="Business date of the FX rate observation.",
        examples=["2026-03-10"],
    )
    rate: Decimal = Field(
        ...,
        description="Observed FX rate for the requested currency pair on the given date.",
        examples=["1.345000"],
    )

    model_config = ConfigDict(from_attributes=True)


class FxRateResponse(BaseModel):
    """
    Represents the API response for an FX rate query.
    """

    from_currency: str = Field(
        ...,
        description="Base currency code for the requested FX series.",
        examples=["USD"],
    )
    to_currency: str = Field(
        ...,
        description="Quote currency code for the requested FX series.",
        examples=["SGD"],
    )
    rates: List[FxRateRecord] = Field(
        ...,
        description="FX rate observations for the requested currency pair and date range.",
    )
