from datetime import date
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field, condecimal


class MarketPrice(BaseModel):
    security_id: str = Field(
        ...,
        description="Canonical security identifier receiving the market-price observation.",
        examples=["SEC_AAPL"],
    )
    price_date: date = Field(
        ...,
        description="Business date for which the market price is valid.",
        examples=["2026-03-10"],
    )
    price: condecimal(gt=Decimal(0)) = Field(
        ...,
        description="Canonical closing or approved valuation price for the security.",
        examples=["175.5000000000"],
    )
    currency: str = Field(
        ...,
        description="Currency in which the market price is quoted.",
        examples=["USD"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "security_id": "SEC_AAPL",
                "price_date": "2026-03-10",
                "price": 175.50,
                "currency": "USD",
            }
        }
    )


class MarketPriceIngestionRequest(BaseModel):
    market_prices: List[MarketPrice] = Field(
        ...,
        description="Market price observations to publish into the valuation reference-data flow.",
        min_length=1,
        examples=[
            [
                {
                    "security_id": "SEC_AAPL",
                    "price_date": "2026-03-10",
                    "price": "175.5000000000",
                    "currency": "USD",
                }
            ]
        ],
    )

