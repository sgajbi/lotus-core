from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PortfolioBenchmarkAssignmentRecord(BaseModel):
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"]
    )
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    effective_from: date = Field(
        ..., description="Assignment effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Assignment effective end date, null for open-ended assignment.",
        examples=["2026-12-31"],
    )
    assignment_source: str = Field(
        ...,
        description="Source channel that established this benchmark assignment.",
        examples=["benchmark_policy_engine"],
    )
    assignment_status: str = Field(..., description="Assignment status.", examples=["active"])
    policy_pack_id: str | None = Field(
        None,
        description="Optional policy pack identifier.",
        examples=["policy_pack_wm_v1"],
    )
    source_system: str | None = Field(
        None, description="Upstream source system.", examples=["lotus-manage"]
    )
    assignment_recorded_at: datetime | None = Field(
        None,
        description=(
            "Optional assignment capture timestamp from the source system; "
            "defaults to ingestion time when omitted."
        ),
        examples=["2026-03-10T08:15:00Z"],
    )
    assignment_version: int = Field(
        1,
        description="Assignment version used for tie-breaks at same effective_from.",
        examples=[1],
        ge=1,
    )

    model_config = ConfigDict()


class PortfolioBenchmarkAssignmentIngestionRequest(BaseModel):
    benchmark_assignments: list[PortfolioBenchmarkAssignmentRecord] = Field(
        ...,
        description="Portfolio benchmark assignment records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "portfolio_id": "DEMO_DPM_EUR_001",
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "effective_from": "2025-01-01",
                    "assignment_source": "benchmark_policy_engine",
                    "assignment_status": "active",
                }
            ]
        ],
    )

    model_config = ConfigDict()
