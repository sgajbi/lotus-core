from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_validator


class SourceObservationLineage(BaseModel):
    source_system: str | None = Field(
        None,
        validation_alias=AliasChoices("source_system", "source_vendor"),
        description=(
            "Canonical upstream source system. Legacy benchmark and market-reference payloads may "
            "still submit source_vendor; ingestion normalizes it into this field before storage."
        ),
        examples=["MSCI"],
    )
    source_record_id: str | None = Field(
        None,
        description="Upstream source record identifier.",
        examples=["source-record-20260102"],
    )
    observed_at: datetime | None = Field(
        None,
        validation_alias=AliasChoices("observed_at", "source_timestamp"),
        description=(
            "Timestamp when the upstream source observed or published this record. Legacy payloads "
            "may still submit source_timestamp; ingestion normalizes it into this field."
        ),
        examples=["2026-01-02T21:00:00Z"],
    )
    quality_status: str = Field(
        "accepted",
        description="Canonical source data-quality status.",
        examples=["accepted"],
    )

    @field_validator("quality_status", mode="before")
    @classmethod
    def _normalize_quality_status(cls, value: object) -> str:
        if value is None:
            return "accepted"
        normalized = str(value).strip().lower()
        if not normalized:
            raise ValueError("quality_status must not be blank")
        return normalized
