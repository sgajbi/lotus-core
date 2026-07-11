"""API contracts for the effective client restriction source product."""

from datetime import date
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class ClientRestrictionProfileRequest(BaseModel):
    """Select effective restrictions for one portfolio and business date."""

    as_of_date: date = Field(
        ...,
        description="Business date used to resolve effective client and mandate restrictions.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and policy-scoped consumers.",
        examples=["default"],
    )
    mandate_id: str | None = Field(
        None,
        description="Optional mandate identifier used to disambiguate portfolio restrictions.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    include_inactive_restrictions: bool = Field(
        False,
        description="When false, excludes inactive or expired restriction records.",
    )

    model_config = ConfigDict()


class ClientRestrictionProfileEntry(BaseModel):
    """One effective client or mandate restriction."""

    restriction_scope: str = Field(
        ...,
        description=(
            "Bounded scope for the restriction such as client, mandate, instrument, issuer, "
            "country, or asset_class."
        ),
        examples=["issuer"],
    )
    restriction_code: str = Field(
        ...,
        description="Machine-readable restriction code safe for downstream proof packs.",
        examples=["NO_PRIVATE_CREDIT_BUY"],
    )
    restriction_status: str = Field(
        ..., description="Restriction lifecycle status selected by the source product."
    )
    restriction_source: str = Field(
        ..., description="Source channel that captured the restriction."
    )
    applies_to_buy: bool = Field(..., description="Whether the restriction applies to buy actions.")
    applies_to_sell: bool = Field(
        ..., description="Whether the restriction applies to sell actions."
    )
    instrument_ids: list[str] = Field(
        default_factory=list, description="Instrument identifiers directly in scope."
    )
    asset_classes: list[str] = Field(
        default_factory=list, description="Asset classes in scope for the restriction."
    )
    issuer_ids: list[str] = Field(
        default_factory=list, description="Issuer identifiers in scope for the restriction."
    )
    country_codes: list[str] = Field(
        default_factory=list, description="Country-of-risk codes in scope for the restriction."
    )
    effective_from: date = Field(..., description="Restriction effective start date.")
    effective_to: date | None = Field(None, description="Restriction effective end date.")
    restriction_version: int = Field(..., description="Selected restriction profile version.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")

    model_config = ConfigDict()


class ClientRestrictionProfileSupportability(BaseModel):
    """Operational readiness of the resolved restriction evidence."""

    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description=(
            "Supportability state for using the client restriction profile in DPM construction."
        ),
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["CLIENT_RESTRICTION_PROFILE_READY"],
    )
    restriction_count: int = Field(
        ..., ge=0, description="Number of effective restrictions returned."
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="Missing source families that block profile consumption.",
    )

    model_config = ConfigDict()


class ClientRestrictionProfileResponse(SourceDataProductRuntimeMetadata):
    """Effective restriction source product with lineage and supportability."""

    product_name: Literal["ClientRestrictionProfile"] = product_name_field(
        "ClientRestrictionProfile"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the profile.")
    client_id: str = Field(..., description="Client identifier bound to the profile.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for profile resolution.")
    restrictions: list[ClientRestrictionProfileEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective client restriction records.",
    )
    supportability: ClientRestrictionProfileSupportability = Field(
        ..., description="Supportability posture for restriction-aware construction."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for restriction profile resolution.",
    )

    model_config = ConfigDict()
