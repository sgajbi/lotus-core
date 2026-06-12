from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BenchmarkReturnSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["series_bmk_60_40_ret"])
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    benchmark_return: Decimal = Field(
        ..., description="Benchmark return value.", examples=["0.0019000000"]
    )
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the benchmark return series.",
        examples=["USD"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the benchmark return series record.",
        examples=["2026-01-02T21:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["bmkr_20260102"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class BenchmarkReturnSeriesIngestionRequest(BaseModel):
    benchmark_return_series: list[BenchmarkReturnSeriesRecord] = Field(
        ...,
        description="Benchmark return series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "series_bmk_60_40_ret",
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "series_date": "2026-01-02",
                    "benchmark_return": "0.0019000000",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                }
            ]
        ],
    )

    model_config = ConfigDict()
