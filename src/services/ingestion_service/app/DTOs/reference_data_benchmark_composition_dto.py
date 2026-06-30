from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .reference_data_source_observation_dto import SourceObservationLineage


class BenchmarkCompositionRecord(SourceObservationLineage):
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
