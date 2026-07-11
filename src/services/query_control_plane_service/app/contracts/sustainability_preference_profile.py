"""API contracts for the effective sustainability preference source product."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class SustainabilityPreferenceProfileRequest(BaseModel):
    """Select effective sustainability preferences for one portfolio and date."""

    as_of_date: date = Field(
        ...,
        description="Business date used to resolve effective sustainability preferences.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and policy-scoped consumers.",
        examples=["default"],
    )
    mandate_id: str | None = Field(
        None,
        description="Optional mandate identifier used to disambiguate portfolio preferences.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    include_inactive_preferences: bool = Field(
        False,
        description="When false, excludes inactive or expired sustainability preference records.",
    )
    model_config = ConfigDict()


class SustainabilityPreferenceProfileEntry(BaseModel):
    """One effective sustainability preference."""

    preference_framework: str = Field(
        ...,
        description="Framework or policy vocabulary for the preference.",
        examples=["LOTUS_SUSTAINABILITY_V1"],
    )
    preference_code: str = Field(
        ...,
        description="Machine-readable sustainability preference code.",
        examples=["MIN_SUSTAINABLE_ALLOCATION"],
    )
    preference_status: str = Field(
        ..., description="Preference lifecycle status selected by the source product."
    )
    preference_source: str = Field(..., description="Source channel that captured the preference.")
    minimum_allocation: Decimal | None = Field(
        None,
        description="Minimum portfolio allocation ratio for the preference, if applicable.",
        examples=["0.2000000000"],
    )
    maximum_allocation: Decimal | None = Field(
        None,
        description="Maximum portfolio allocation ratio for the preference, if applicable.",
        examples=["0.0500000000"],
    )
    applies_to_asset_classes: list[str] = Field(
        default_factory=list, description="Asset classes in scope for the preference."
    )
    exclusion_codes: list[str] = Field(
        default_factory=list, description="Sustainability exclusion codes in scope."
    )
    positive_tilt_codes: list[str] = Field(
        default_factory=list, description="Positive sustainability tilt codes in scope."
    )
    effective_from: date = Field(..., description="Preference effective start date.")
    effective_to: date | None = Field(None, description="Preference effective end date.")
    preference_version: int = Field(..., description="Selected preference profile version.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")
    model_config = ConfigDict()


class SustainabilityPreferenceProfileSupportability(BaseModel):
    """Operational readiness of the resolved preference evidence."""

    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description=(
            "Supportability state for using sustainability preferences in DPM construction."
        ),
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["SUSTAINABILITY_PREFERENCE_PROFILE_READY"],
    )
    preference_count: int = Field(
        ..., ge=0, description="Number of effective preferences returned."
    )
    missing_data_families: list[str] = Field(
        default_factory=list, description="Missing source families that block profile consumption."
    )
    model_config = ConfigDict()


class SustainabilityPreferenceProfileResponse(SourceDataProductRuntimeMetadata):
    """Effective preference source product with lineage and supportability."""

    product_name: Literal["SustainabilityPreferenceProfile"] = product_name_field(
        "SustainabilityPreferenceProfile"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the profile.")
    client_id: str = Field(..., description="Client identifier bound to the profile.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for profile resolution.")
    preferences: list[SustainabilityPreferenceProfileEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective sustainability preference records.",
    )
    supportability: SustainabilityPreferenceProfileSupportability = Field(
        ..., description="Supportability posture for sustainability-aware construction."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for sustainability preference profile resolution.",
    )
    model_config = ConfigDict()
