from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .reference_data_source_observation_dto import SourceObservationLineage


class IndexReturnSeriesRecord(SourceObservationLineage):
    series_id: str = Field(..., description="Series identifier.", examples=["series_idx_world_ret"])
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_return: Decimal = Field(..., description="Index return value.", examples=["0.0023000000"])
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the index return series.",
        examples=["USD"],
    )

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class IndexReturnSeriesIngestionRequest(BaseModel):
    index_return_series: list[IndexReturnSeriesRecord] = Field(
        ...,
        description="Index return series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "series_idx_world_ret",
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "series_date": "2026-01-02",
                    "index_return": "0.0023000000",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                }
            ]
        ],
    )

    model_config = ConfigDict()
