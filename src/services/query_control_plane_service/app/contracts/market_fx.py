"""Explicit source selection and retained FX provenance within market windows."""

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class FxSourceSelectionRequest(BaseModel):
    """No caller tenant, enrollment, priority or implied latest-provider authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(
        min_length=1,
        max_length=128,
        description="Explicit retained provider namespace.",
        examples=["provider-synthetic-controls"],
    )
    source_id: str = Field(
        min_length=1,
        max_length=128,
        description="Explicit retained source feed namespace.",
        examples=["feed-synthetic-close"],
    )
    source_as_of: AwareDatetime = Field(
        description="Inclusive source observation boundary, not Core knowledge time.",
        examples=["2026-10-08T16:00:00Z"],
    )
    known_as_of: AwareDatetime = Field(
        description="Inclusive Core acceptance boundary; late admissions are excluded.",
        examples=["2026-10-08T16:05:00Z"],
    )
    cut_id: str | None = Field(
        default=None,
        pattern="^[0-9a-f]{64}$",
        description="Optional server-derived retained cut; exact membership stays immutable.",
        examples=["a" * 64],
    )


class FxSourceEvidenceResponse(BaseModel):
    """Retained software authority is not institutional provider certification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rate_date: date
    provider_id: str
    source_id: str
    revision_id: str
    content_hash: str
    source_observed_at: AwareDatetime
    accepted_at: AwareDatetime
    fixing_kind: str
    calendar_version: str
    cut_id: str
