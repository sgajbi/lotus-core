"""Retained source facts for existing analytics export result contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsExportPageEvidence(BaseModel):
    page_number: int = Field(..., ge=1, description="One-based acquisition order.", examples=[1])
    row_count: int = Field(..., ge=0, description="Actual collected page rows.", examples=[2000])
    requested_scope: dict[str, object] = Field(
        ..., description="Exact requested business scope, excluding transport continuation."
    )
    source_metadata: dict[str, object] = Field(
        ..., description="Source response facts excluding data rows; never reconstructed on reads."
    )
    model_config = ConfigDict(extra="forbid")


class AnalyticsExportSourceEvidence(BaseModel):
    selection_digest: str | None = Field(
        None,
        pattern=r"^sha256:[0-9a-f]{64}$",
        description=(
            "Server-derived identity of acquired export rows and retained source facts, excluding "
            "serving timestamps and continuation tokens. "
            "Not source-cut, provider or approval authority. "
            "Null for older exports without this identity."
        ),
    )
    manifest_version: Literal["analytics_export_source_evidence_v1"] = Field(
        "analytics_export_source_evidence_v1", description="Retained evidence manifest schema."
    )
    availability: Literal["RETAINED", "UNAVAILABLE"] = Field(
        "UNAVAILABLE", description="Whether page evidence was retained when the export completed."
    )
    source_cut_status: Literal["AVAILABLE", "UNAVAILABLE"] = Field(
        "UNAVAILABLE", description="AVAILABLE only when every page emitted the same known cut."
    )
    source_cut_id: str | None = Field(
        None, description="Unchanged common source-owned cut, not a synthesized export hash."
    )
    source_evidence_current: bool = Field(
        False, description="True only when every retained page reports current source evidence."
    )
    quality_statuses: list[str] = Field(
        default_factory=list, description="All distinct page quality states in acquisition order."
    )
    freshness_statuses: list[str] = Field(
        default_factory=list, description="All distinct page freshness states in acquisition order."
    )
    unavailable_reasons: list[str] = Field(
        default_factory=lambda: ["LEGACY_EXPORT_SOURCE_EVIDENCE_NOT_RETAINED"],
        description="Deterministic missing-evidence reasons; exact source reasons remain on pages.",
    )
    pages: list[AnalyticsExportPageEvidence] = Field(
        default_factory=list, description="Ordered retained evidence, including empty pages."
    )
    model_config = ConfigDict(extra="forbid")
