from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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
