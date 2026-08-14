"""Shared value contracts for query-control-plane integration products."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class IntegrationWindow(BaseModel):
    start_date: date = Field(
        ...,
        description="Window start date for series retrieval (inclusive).",
        examples=["2026-01-01"],
    )
    end_date: date = Field(
        ...,
        description="Window end date for series retrieval (inclusive).",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()


class SourceObservationEvidence(BaseModel):
    """Canonical upstream observation fields preserved on query records."""

    source_system: str | None = Field(
        None, description="Canonical upstream source system.", examples=["MSCI"]
    )
    source_record_id: str | None = Field(
        None, description="Upstream source record identifier.", examples=["record-20260102"]
    )
    observed_at: datetime | None = Field(
        None,
        description="Timestamp when the upstream source observed or published the record.",
        examples=["2026-01-02T21:00:00Z"],
    )
    quality_status: str = Field(
        ..., description="Persisted source data-quality status.", examples=["accepted"]
    )
