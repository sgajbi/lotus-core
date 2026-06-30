from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .reference_data_source_observation_dto import SourceObservationLineage


class IndexPriceSeriesRecord(SourceObservationLineage):
    series_id: str = Field(
        ..., description="Series identifier.", examples=["series_idx_world_price"]
    )
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_price: Decimal = Field(
        ...,
        gt=Decimal(0),
        description="Index price value.",
        examples=["4567.1234000000"],
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the index price series.",
        examples=["USD"],
    )
    value_convention: str = Field(
        ..., description="Value convention label.", examples=["close_price"]
    )

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class IndexPriceSeriesIngestionRequest(BaseModel):
    index_price_series: list[IndexPriceSeriesRecord] = Field(
        ...,
        description="Index price series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "series_idx_world_price",
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "series_date": "2026-01-02",
                    "index_price": "4567.1234000000",
                    "series_currency": "USD",
                    "value_convention": "close_price",
                }
            ]
        ],
    )

    model_config = ConfigDict()
