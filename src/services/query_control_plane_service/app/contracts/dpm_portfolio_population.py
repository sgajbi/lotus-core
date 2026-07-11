"""API contracts for CIO cohorts and DPM portfolio populations."""

from datetime import date, datetime
from typing import Literal

from portfolio_common.reference_data_paging import ReferencePageMetadata, ReferencePageRequest
from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class CioModelChangeAffectedCohortRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve the approved model version and mandate cohort.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and policy-scoped consumers.",
        examples=["default"],
    )
    booking_center_code: str | None = Field(
        None,
        description="Optional booking-center filter for regional CIO model-change rollout.",
        examples=["Singapore"],
    )
    include_inactive_mandates: bool = Field(
        False,
        description=(
            "When false, only active discretionary authority bindings are returned. Inactive "
            "bindings remain source-visible future scope for exception dashboards."
        ),
    )
    model_config = ConfigDict()


class CioModelChangeAffectedMandate(BaseModel):
    portfolio_id: str = Field(..., description="Affected portfolio identifier.")
    mandate_id: str = Field(..., description="Affected discretionary mandate identifier.")
    client_id: str = Field(..., description="Client identifier bound to the mandate.")
    booking_center_code: str = Field(..., description="Booking center governing the mandate.")
    jurisdiction_code: str = Field(..., description="Jurisdiction governing the mandate.")
    discretionary_authority_status: str = Field(
        ..., description="Discretionary authority status selected by the source product."
    )
    model_portfolio_id: str = Field(..., description="Approved model portfolio identifier.")
    policy_pack_id: str | None = Field(
        None, description="Policy pack associated with the mandate binding, when available."
    )
    risk_profile: str = Field(..., description="Mandate risk profile.")
    effective_from: date = Field(..., description="Binding effective start date.")
    effective_to: date | None = Field(
        None, description="Binding effective end date, null when open-ended."
    )
    binding_version: int = Field(..., description="Selected binding version.")
    source_record_id: str | None = Field(
        None, description="Source record id for mandate-cohort audit and replay."
    )
    model_config = ConfigDict()


class CioModelChangeAffectedCohortSupportability(BaseModel):
    state: Literal["READY", "INCOMPLETE"] = Field(
        ...,
        description="Supportability state for CIO model-change cohort consumption.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["CIO_MODEL_CHANGE_COHORT_READY"],
    )
    returned_mandate_count: int = Field(
        ..., ge=0, description="Number of affected mandate bindings returned.", examples=[1]
    )
    filters_applied: list[str] = Field(
        default_factory=list,
        description="Filters applied by the source product.",
        examples=[["model_portfolio_id", "as_of_date", "active_discretionary_authority"]],
    )
    model_config = ConfigDict()


class CioModelChangeAffectedCohortResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["CioModelChangeAffectedCohort"] = product_name_field(
        "CioModelChangeAffectedCohort"
    )
    product_version: Literal["v1"] = product_version_field()
    model_portfolio_id: str = Field(
        ...,
        description="Approved model portfolio identifier used to discover affected mandates.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version selected for the as-of date.",
        examples=["2026.05"],
    )
    model_change_event_id: str = Field(
        ...,
        description=(
            "Deterministic source-owned event identity for this approved model version and "
            "affected cohort scope."
        ),
        examples=["cio_model_change:MODEL_PB_SG_GLOBAL_BAL_DPM:2026.05:2026-05-03"],
    )
    approval_state: str = Field(
        ...,
        description="Model definition approval state selected by the source product.",
        examples=["approved"],
    )
    approved_at: datetime | None = Field(
        None, description="Timestamp when the selected model version was approved, if available."
    )
    effective_from: date = Field(
        ...,
        description="Selected model version effective start date.",
        examples=["2026-05-01"],
    )
    effective_to: date | None = Field(
        None, description="Selected model version effective end date, null when open-ended."
    )
    affected_mandates: list[CioModelChangeAffectedMandate] = Field(
        default_factory=list,
        description="Deterministically ordered affected discretionary mandates.",
    )
    supportability: CioModelChangeAffectedCohortSupportability = Field(
        ..., description="Readiness posture for automatic CIO model-change wave discovery."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for model definition and mandate binding discovery.",
    )
    model_config = ConfigDict()


class DpmPortfolioUniverseCandidateRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve effective DPM portfolio-universe candidates.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and policy-scoped consumers.",
        examples=["default"],
    )
    booking_center_code: str | None = Field(
        None,
        description="Optional booking-center filter for regional DPM universe discovery.",
        examples=["Singapore"],
    )
    model_portfolio_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional approved model portfolio identifiers used to narrow the DPM candidate "
            "universe. Empty means all effective discretionary mandate bindings in scope."
        ),
        examples=[["MODEL_PB_SG_GLOBAL_BAL_DPM", "MODEL_PB_SG_INCOME_DPM"]],
    )
    include_inactive_mandates: bool = Field(
        False,
        description=(
            "When false, only active discretionary authority bindings are returned. Inactive "
            "bindings remain source-visible for exception dashboards only when explicitly "
            "requested."
        ),
    )
    page: ReferencePageRequest = Field(
        default_factory=ReferencePageRequest,
        description="Deterministic paging controls for large DPM portfolio-universe cohorts.",
    )
    model_config = ConfigDict()


class DpmPortfolioUniverseCandidate(BaseModel):
    portfolio_id: str = Field(..., description="Candidate portfolio identifier.")
    mandate_id: str = Field(..., description="Source-owned discretionary mandate identifier.")
    client_id: str = Field(..., description="Client identifier bound to the mandate.")
    booking_center_code: str = Field(..., description="Booking center governing the mandate.")
    jurisdiction_code: str = Field(..., description="Jurisdiction governing the mandate.")
    discretionary_authority_status: str = Field(
        ..., description="Discretionary authority status selected by the source product."
    )
    model_portfolio_id: str = Field(..., description="Approved model portfolio identifier.")
    policy_pack_id: str | None = Field(
        None, description="Policy pack associated with the mandate binding, when available."
    )
    mandate_objective: str | None = Field(
        None, description="Mandate objective carried by the source-owned binding."
    )
    risk_profile: str = Field(..., description="Mandate risk profile.")
    investment_horizon: str = Field(..., description="Mandate investment horizon.")
    effective_from: date = Field(..., description="Binding effective start date.")
    effective_to: date | None = Field(
        None, description="Binding effective end date, null when open-ended."
    )
    binding_version: int = Field(..., description="Selected binding version.")
    source_record_id: str | None = Field(
        None, description="Source record id for universe-candidate audit and replay."
    )
    model_config = ConfigDict()


class DpmPortfolioUniverseCandidateSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE"] = Field(
        ...,
        description="Supportability state for DPM portfolio-universe candidate discovery.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["DPM_PORTFOLIO_UNIVERSE_READY"],
    )
    returned_candidate_count: int = Field(
        ...,
        ge=0,
        description="Number of candidate mandate bindings returned in the current page.",
        examples=[250],
    )
    filters_applied: list[str] = Field(
        default_factory=list,
        description="Filters applied by the source product.",
        examples=[["as_of_date", "active_discretionary_authority", "booking_center_code"]],
    )
    page_truncated: bool = Field(
        ..., description="True when additional candidates remain behind the continuation token."
    )
    model_config = ConfigDict()


class DpmPortfolioUniverseCandidateSelectionBasis(BaseModel):
    basis_type: Literal["EFFECTIVE_DISCRETIONARY_MANDATE_BINDING"] = Field(
        ...,
        description=(
            "Source-owned selection-basis code declaring that candidate membership is resolved "
            "from effective discretionary mandate bindings, not inferred by advisory campaign "
            "or relationship workflow state."
        ),
        examples=["EFFECTIVE_DISCRETIONARY_MANDATE_BINDING"],
    )
    source_table: Literal["portfolio_mandate_bindings"] = Field(
        ...,
        description="Core source table family used to resolve DPM portfolio-universe candidates.",
        examples=["portfolio_mandate_bindings"],
    )
    included_when: list[str] = Field(
        default_factory=list,
        description=(
            "Deterministic source predicates that must hold before a mandate binding can appear "
            "as a DPM portfolio-universe candidate."
        ),
        examples=[
            [
                "mandate_type=discretionary",
                "effective_from<=as_of_date",
                "effective_to is null or effective_to>=as_of_date",
                "active authority unless include_inactive_mandates=true",
            ]
        ],
    )
    downstream_boundary: str = Field(
        ...,
        description=(
            "Source-authority boundary for the candidate-selection basis. This prevents "
            "candidate membership from being promoted into unsupported relationship, suitability, "
            "manager-assignment, trading-authorization, client-notification, or external-process "
            "authority."
        ),
        examples=[
            (
                "Candidate membership is not relationship householding, suitability approval, "
                "manager assignment, trading authorization, client notification authority, or "
                "external process ownership."
            )
        ],
    )
    model_config = ConfigDict()


class DpmPortfolioUniverseCandidateResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DpmPortfolioUniverseCandidate"] = product_name_field(
        "DpmPortfolioUniverseCandidate"
    )
    product_version: Literal["v1"] = product_version_field()
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve candidate membership.",
        examples=["2026-05-03"],
    )
    candidates: list[DpmPortfolioUniverseCandidate] = Field(
        default_factory=list,
        description=(
            "Deterministically ordered Core-owned DPM portfolio-universe candidates selected "
            "from effective discretionary mandate bindings."
        ),
    )
    page: ReferencePageMetadata = Field(
        ..., description="Paging metadata for the returned candidate page."
    )
    supportability: DpmPortfolioUniverseCandidateSupportability = Field(
        ..., description="Readiness posture for automatic DPM portfolio-universe discovery."
    )
    selection_basis: DpmPortfolioUniverseCandidateSelectionBasis = Field(
        ...,
        description=(
            "Source-owned rule basis explaining why returned mandate bindings qualify as DPM "
            "portfolio-universe candidates."
        ),
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for DPM portfolio-universe candidate discovery.",
    )
    model_config = ConfigDict()
