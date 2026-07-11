"""Public contracts for effective portfolio benchmark assignment evidence."""

from datetime import date, datetime
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class BenchmarkAssignmentPolicyContext(BaseModel):
    """Optional caller context retained for contract compatibility and lineage."""

    tenant_id: str | None = Field(
        None,
        description="Tenant identifier for policy-scoped data resolution.",
        examples=["tenant_sg_pb"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier used for deterministic assignment resolution.",
        examples=["policy_pack_wm_v1"],
    )

    model_config = ConfigDict()


class BenchmarkAssignmentRequest(BaseModel):
    """Point-in-time benchmark assignment resolution request."""

    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the active benchmark assignment.",
        examples=["2026-01-31"],
    )
    reporting_currency: str | None = Field(
        None,
        description=(
            "Optional request context currency for caller symmetry and lineage. "
            "This field does not change benchmark assignment selection."
        ),
        examples=["USD"],
    )
    policy_context: BenchmarkAssignmentPolicyContext | None = Field(
        None,
        description=(
            "Optional tenant/policy context reserved for governance metadata and future "
            "policy-bound resolution. The current implementation still resolves the "
            "effective assignment by portfolio_id and as_of_date."
        ),
    )

    model_config = ConfigDict()


class BenchmarkAssignmentResponse(SourceDataProductRuntimeMetadata):
    """Effective assignment with source-owned deterministic evidence metadata."""

    product_name: Literal["BenchmarkAssignment"] = product_name_field("BenchmarkAssignment")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"]
    )
    benchmark_id: str = Field(
        ..., description="Canonical benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    as_of_date: date = Field(
        ..., description="As-of date used to resolve the assignment.", examples=["2026-01-31"]
    )
    effective_from: date = Field(
        ..., description="Assignment effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Assignment effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    assignment_source: str = Field(
        ...,
        description="Source channel that established the assignment.",
        examples=["benchmark_policy_engine"],
    )
    assignment_status: str = Field(
        ..., description="Assignment lifecycle status.", examples=["active"]
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier associated with the assignment record.",
        examples=["policy_pack_wm_v1"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system identifier.",
        examples=["mandate-booking-system"],
    )
    assignment_recorded_at: datetime = Field(
        ...,
        description="Timestamp when lotus-core captured the assignment record.",
        examples=["2026-01-31T09:15:00Z"],
    )
    assignment_version: int = Field(
        ...,
        description="Monotonic assignment version for effective-date ties.",
        examples=[3],
    )
    contract_version: str = Field(
        "rfc_062_v1",
        description="Benchmark assignment integration contract version.",
        examples=["rfc_062_v1"],
    )

    model_config = ConfigDict()
