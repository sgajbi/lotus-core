from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, condecimal, model_validator


class ClientRestrictionProfileRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the restriction profile.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the restriction profile.")
    mandate_id: str | None = Field(
        None, description="Mandate identifier when the restriction is mandate-specific."
    )
    restriction_scope: Literal[
        "client", "mandate", "instrument", "issuer", "country", "asset_class"
    ] = Field(..., description="Bounded restriction scope.")
    restriction_code: str = Field(
        ..., description="Machine-readable restriction code.", examples=["NO_PRIVATE_CREDIT_BUY"]
    )
    restriction_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Restriction lifecycle status."
    )
    restriction_source: str = Field(
        ..., description="Source channel that captured the restriction."
    )
    applies_to_buy: bool = Field(True, description="Whether the restriction applies to buys.")
    applies_to_sell: bool = Field(False, description="Whether the restriction applies to sells.")
    instrument_ids: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    issuer_ids: list[str] = Field(default_factory=list)
    country_codes: list[str] = Field(default_factory=list)
    effective_from: date = Field(..., description="Restriction effective start date.")
    effective_to: date | None = Field(None, description="Restriction effective end date.")
    restriction_version: int = Field(1, ge=1)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @model_validator(mode="after")
    def validate_effective_window(self) -> "ClientRestrictionProfileRecord":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        scoped_values = (
            self.instrument_ids or self.asset_classes or self.issuer_ids or self.country_codes
        )
        if self.restriction_scope not in {"client", "mandate"} and not scoped_values:
            raise ValueError("scoped restrictions must include at least one scoped identifier")
        return self

    model_config = ConfigDict()


class SustainabilityPreferenceProfileRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the preference profile.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the preference profile.")
    mandate_id: str | None = Field(
        None, description="Mandate identifier when the preference is mandate-specific."
    )
    preference_framework: str = Field(
        ..., description="Framework or policy vocabulary for the preference."
    )
    preference_code: str = Field(
        ..., description="Machine-readable sustainability preference code."
    )
    preference_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Preference lifecycle status."
    )
    preference_source: str = Field(..., description="Source channel that captured the preference.")
    minimum_allocation: condecimal(ge=Decimal(0), le=Decimal(1)) | None = Field(None)
    maximum_allocation: condecimal(ge=Decimal(0), le=Decimal(1)) | None = Field(None)
    applies_to_asset_classes: list[str] = Field(default_factory=list)
    exclusion_codes: list[str] = Field(default_factory=list)
    positive_tilt_codes: list[str] = Field(default_factory=list)
    effective_from: date = Field(..., description="Preference effective start date.")
    effective_to: date | None = Field(None, description="Preference effective end date.")
    preference_version: int = Field(1, ge=1)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @model_validator(mode="after")
    def validate_profile(self) -> "SustainabilityPreferenceProfileRecord":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        if (
            self.minimum_allocation is not None
            and self.maximum_allocation is not None
            and self.minimum_allocation > self.maximum_allocation
        ):
            raise ValueError("minimum_allocation must be less than or equal to maximum_allocation")
        if not (
            self.exclusion_codes or self.positive_tilt_codes or self.minimum_allocation is not None
        ):
            raise ValueError(
                "sustainability preference must include an exclusion, tilt, or allocation bound"
            )
        return self

    model_config = ConfigDict()


class ClientRestrictionProfileIngestionRequest(BaseModel):
    restriction_profiles: list[ClientRestrictionProfileRecord] = Field(
        ...,
        description="Effective-dated client restriction profile records to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_profile_uniqueness(self) -> "ClientRestrictionProfileIngestionRequest":
        keys = [
            (
                profile.client_id,
                profile.portfolio_id,
                profile.restriction_code,
                profile.effective_from,
                profile.restriction_version,
            )
            for profile in self.restriction_profiles
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("restriction_profiles contains duplicate effective records")
        return self

    model_config = ConfigDict()


class SustainabilityPreferenceProfileIngestionRequest(BaseModel):
    sustainability_preferences: list[SustainabilityPreferenceProfileRecord] = Field(
        ...,
        description=(
            "Effective-dated sustainability preference profile records to ingest or upsert."
        ),
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_preference_uniqueness(
        self,
    ) -> "SustainabilityPreferenceProfileIngestionRequest":
        keys = [
            (
                profile.client_id,
                profile.portfolio_id,
                profile.preference_framework,
                profile.preference_code,
                profile.effective_from,
                profile.preference_version,
            )
            for profile in self.sustainability_preferences
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("sustainability_preferences contains duplicate effective records")
        return self

    model_config = ConfigDict()
