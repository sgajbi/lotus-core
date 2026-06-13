from __future__ import annotations

from datetime import date, datetime
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
