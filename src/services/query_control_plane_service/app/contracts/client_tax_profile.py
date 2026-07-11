"""API contracts for the effective client tax-profile source product."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class ClientTaxProfileRequest(BaseModel):
    """Select effective tax-reference profiles for one portfolio and date."""

    as_of_date: date = Field(
        ...,
        description="Business date used to resolve effective client tax profile records.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and policy-scoped consumers.",
        examples=["default"],
    )
    mandate_id: str | None = Field(
        None,
        description="Optional mandate identifier used to disambiguate portfolio tax profiles.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    include_inactive_profiles: bool = Field(
        False, description="When false, excludes inactive or expired tax profile records."
    )
    model_config = ConfigDict()


class ClientTaxProfileEntry(BaseModel):
    """One effective client tax-reference profile."""

    tax_profile_id: str = Field(..., description="Source-owned tax profile identifier.")
    tax_residency_country: str = Field(..., description="Client tax-residency country.")
    booking_tax_jurisdiction: str = Field(..., description="Booking-center tax jurisdiction.")
    tax_status: str = Field(..., description="Bounded tax status from the source product.")
    profile_status: str = Field(..., description="Tax profile lifecycle status.")
    withholding_tax_rate: Decimal | None = Field(
        None, description="Reference withholding rate ratio when supplied by the source."
    )
    capital_gains_tax_applicable: bool = Field(
        ..., description="Whether source evidence marks capital gains tax as applicable."
    )
    income_tax_applicable: bool = Field(
        ..., description="Whether source evidence marks income tax as applicable."
    )
    treaty_codes: list[str] = Field(default_factory=list)
    eligible_account_types: list[str] = Field(default_factory=list)
    effective_from: date = Field(..., description="Tax profile effective start date.")
    effective_to: date | None = Field(None, description="Tax profile effective end date.")
    profile_version: int = Field(..., description="Selected tax profile version.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")
    model_config = ConfigDict()


class ClientTaxProfileSupportability(BaseModel):
    """Operational readiness of the resolved tax-reference evidence."""

    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using client tax profiles as DPM evidence.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["CLIENT_TAX_PROFILE_READY"],
    )
    profile_count: int = Field(..., ge=0, description="Number of effective profiles returned.")
    missing_data_families: list[str] = Field(default_factory=list)
    model_config = ConfigDict()


class ClientTaxProfileResponse(SourceDataProductRuntimeMetadata):
    """Effective tax-reference source product with lineage and supportability."""

    product_name: Literal["ClientTaxProfile"] = product_name_field("ClientTaxProfile")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the profile.")
    client_id: str = Field(..., description="Client identifier bound to the profile.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for profile resolution.")
    profiles: list[ClientTaxProfileEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective client tax profile records.",
    )
    supportability: ClientTaxProfileSupportability = Field(
        ..., description="Supportability posture for tax-reference evidence."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict, description="Source lineage for tax profile resolution."
    )
    model_config = ConfigDict()
