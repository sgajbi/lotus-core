"""API contracts for market and reference coverage diagnostics."""

from datetime import date
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field

from .common import IntegrationWindow


class CoverageRequest(BaseModel):
    """Request coverage diagnostics for an inclusive observation window."""

    window: IntegrationWindow = Field(..., description="Coverage observation window.")

    model_config = ConfigDict()


class CoverageResponse(SourceDataProductRuntimeMetadata):
    """Source-data coverage, quality, freshness, and lineage evidence."""

    product_name: Literal["DataQualityCoverageReport"] = product_name_field(
        "DataQualityCoverageReport"
    )
    product_version: Literal["v1"] = product_version_field()
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the coverage diagnostics scope.",
        examples=["2cb014be96ad2cb65ce1833d9f2b88a2"],
    )
    coverage_report_id: str = Field(
        ...,
        description="Deterministic identity for this exact data-quality coverage report.",
        examples=["dqc_0123456789abcdef0123456789abcdef"],
    )
    observed_start_date: date | None = Field(
        None,
        description="Observed first date in data window.",
        examples=["2026-01-01"],
    )
    observed_end_date: date | None = Field(
        None,
        description="Observed last date in data window.",
        examples=["2026-01-31"],
    )
    expected_start_date: date = Field(
        ...,
        description="Expected start date from request window.",
        examples=["2026-01-01"],
    )
    expected_end_date: date = Field(
        ...,
        description="Expected end date from request window.",
        examples=["2026-01-31"],
    )
    total_points: int = Field(
        ...,
        description="Total points available in observed window.",
        examples=[31],
    )
    required_count: int = Field(
        ...,
        ge=0,
        description="Required observation count for the inclusive requested window.",
        examples=[31],
    )
    observed_count: int = Field(
        ...,
        ge=0,
        description="Distinct required-scope dates with complete observed source coverage.",
        examples=[29],
    )
    missing_dates_count: int = Field(
        ...,
        description="Count of missing calendar dates within expected window.",
        examples=[2],
    )
    missing_dates_sample: list[date] = Field(
        default_factory=list,
        description="Sample of missing dates in the expected window.",
        examples=[["2026-01-10", "2026-01-21"]],
    )
    quality_status_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Quality status distribution over observed points.",
        examples=[{"accepted": 29, "estimated": 2}],
    )
    stale_count: int = Field(
        ...,
        ge=0,
        description="Observed source records classified with stale quality.",
        examples=[1],
    )
    blocking_issue_count: int = Field(
        ...,
        ge=0,
        description="Observed source records carrying a blocking quality classification.",
        examples=[0],
    )
    warning_issue_count: int = Field(
        ...,
        ge=0,
        description="Observed source records carrying partial or warning quality.",
        examples=[2],
    )
    freshness_threshold_minutes: int = Field(
        ...,
        ge=0,
        description="Freshness threshold applied to the latest contributing evidence.",
        examples=[1440],
    )
    evidence_age_minutes: int | None = Field(
        None,
        ge=0,
        description="Whole-minute age of the latest contributing source evidence.",
        examples=[60],
    )
    contributing_evidence_refs: list[str] = Field(
        default_factory=list,
        description="Deterministic source-owned references contributing to this report.",
    )
    publication_gate: Literal["ALLOW", "BLOCK"] = Field(
        ...,
        description="Fail-closed downstream usage decision for this coverage report.",
        examples=["ALLOW"],
    )
    publication_block_reasons: list[str] = Field(
        default_factory=list,
        description="Bounded reasons why downstream use of this coverage report is blocked.",
    )

    model_config = ConfigDict()
