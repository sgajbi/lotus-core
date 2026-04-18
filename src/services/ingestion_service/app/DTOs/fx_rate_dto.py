from datetime import date
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field, condecimal


class FxRate(BaseModel):
    from_currency: str = Field(
        ...,
        description="Currency being converted from in the canonical FX pair.",
        examples=["USD"],
    )
    to_currency: str = Field(
        ...,
        description="Currency being converted to in the canonical FX pair.",
        examples=["SGD"],
    )
    rate_date: date = Field(
        ...,
        description="Business date for which the FX rate is valid.",
        examples=["2026-03-10"],
    )
    rate: condecimal(gt=Decimal(0)) = Field(
        ...,
        description=(
            "FX conversion rate expressed as units of `to_currency` per "
            "one unit of `from_currency`."
        ),
        examples=["1.3500000000"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "from_currency": "USD",
                "to_currency": "SGD",
                "rate_date": "2026-03-10",
                "rate": 1.35,
            }
        }
    )


class FxRateIngestionRequest(BaseModel):
    fx_rates: List[FxRate] = Field(
        ...,
        description=(
            "FX reference-rate observations to publish into valuation and conversion workflows."
        ),
        min_length=1,
        examples=[
            [
                {
                    "from_currency": "USD",
                    "to_currency": "SGD",
                    "rate_date": "2026-03-10",
                    "rate": "1.3500000000",
                }
            ]
        ],
    )
