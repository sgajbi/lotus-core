from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_validator

from .ingestion_validation_errors import (
    INVALID_OBSERVED_AT,
    INVALID_QUALITY_STATUS,
    raise_ingestion_validation_error,
)


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
        if not isinstance(value, str):
            raise_ingestion_validation_error(
                INVALID_QUALITY_STATUS,
                field_path="quality_status",
                message="quality_status must be a string",
            )
        normalized = value.strip().lower()
        if not normalized:
            raise_ingestion_validation_error(
                INVALID_QUALITY_STATUS,
                field_path="quality_status",
                message="quality_status must not be blank",
            )
        return normalized

    @field_validator("observed_at")
    @classmethod
    def _require_timezone_aware_observation(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise_ingestion_validation_error(
                INVALID_OBSERVED_AT,
                field_path="observed_at",
                message="observed_at must include a timezone offset",
            )
        return value
