from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BenchmarkDefinitionRecord(BaseModel):
    benchmark_id: str = Field(
        ..., description="Canonical benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    benchmark_name: str = Field(
        ..., description="Benchmark display name.", examples=["Global Balanced 60/40 (TR)"]
    )
    benchmark_type: Literal["single_index", "composite"] = Field(
        ...,
        description="Benchmark type.",
        examples=["composite"],
    )
    benchmark_currency: str = Field(
        ...,
        description=(
            "Canonical three-letter benchmark currency used for performance comparison, "
            "policy evidence, and reporting alignment."
        ),
        examples=["USD"],
    )
    return_convention: Literal["price_return_index", "total_return_index"] = Field(
        ...,
        description="Benchmark return convention.",
        examples=["total_return_index"],
    )
    benchmark_status: str = Field("active", description="Benchmark status.", examples=["active"])
    benchmark_family: str | None = Field(
        None,
        description="Benchmark family grouping.",
        examples=["multi_asset_strategic"],
    )
    benchmark_provider: str | None = Field(
        None,
        description="Benchmark provider name.",
        examples=["MSCI"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Rebalance frequency for composite benchmarks.",
        examples=["quarterly"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Canonical classification labels.",
        examples=[{"asset_class": "multi_asset", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None, description="Definition effective end date.", examples=["2026-12-31"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the benchmark definition payload.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["bmk_v20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("benchmark_currency", mode="before")
    @classmethod
    def _normalize_benchmark_currency(cls, value: object) -> str:
        return cast(str, normalize_currency_code(value))

    model_config = ConfigDict()


class BenchmarkCompositionRecord(BaseModel):
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    index_id: str = Field(
        ..., description="Component index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    composition_effective_from: date = Field(
        ...,
        description="Composition effective start date.",
        examples=["2026-01-01"],
    )
    composition_effective_to: date | None = Field(
        None,
        description="Composition effective end date.",
        examples=["2026-03-31"],
    )
    composition_weight: Decimal = Field(
        ...,
        ge=Decimal(0),
        le=Decimal(1),
        description="Component weight between 0 and 1.",
        examples=["0.6000000000"],
    )
    rebalance_event_id: str | None = Field(
        None,
        description="Rebalance event identifier.",
        examples=["rebalance_2026q1"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the benchmark composition payload.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["cmp_v20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


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


class BenchmarkDefinitionIngestionRequest(BaseModel):
    benchmark_definitions: list[BenchmarkDefinitionRecord] = Field(
        ...,
        description="Benchmark definition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "benchmark_name": "Global Balanced 60/40 (TR)",
                    "benchmark_type": "composite",
                    "benchmark_currency": "USD",
                    "return_convention": "total_return_index",
                    "effective_from": "2025-01-01",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class BenchmarkCompositionIngestionRequest(BaseModel):
    benchmark_compositions: list[BenchmarkCompositionRecord] = Field(
        ...,
        description="Benchmark composition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "composition_effective_from": "2026-01-01",
                    "composition_weight": "0.6000000000",
                }
            ]
        ],
    )

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
