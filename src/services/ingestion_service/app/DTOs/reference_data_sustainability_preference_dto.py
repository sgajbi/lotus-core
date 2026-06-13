from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AllocationBound = Annotated[Decimal, Field(ge=Decimal(0), le=Decimal(1))]


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
    minimum_allocation: AllocationBound | None = Field(None)
    maximum_allocation: AllocationBound | None = Field(None)
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
        _validate_effective_window(self.effective_from, self.effective_to)
        _validate_allocation_bounds(self.minimum_allocation, self.maximum_allocation)
        _validate_preference_substance(
            exclusion_codes=self.exclusion_codes,
            positive_tilt_codes=self.positive_tilt_codes,
            minimum_allocation=self.minimum_allocation,
        )
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


def _validate_effective_window(effective_from: date, effective_to: date | None) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to must be on or after effective_from")


def _validate_allocation_bounds(
    minimum_allocation: Decimal | None, maximum_allocation: Decimal | None
) -> None:
    if (
        minimum_allocation is not None
        and maximum_allocation is not None
        and minimum_allocation > maximum_allocation
    ):
        raise ValueError("minimum_allocation must be less than or equal to maximum_allocation")


def _validate_preference_substance(
    *,
    exclusion_codes: list[str],
    positive_tilt_codes: list[str],
    minimum_allocation: Decimal | None,
) -> None:
    if not (exclusion_codes or positive_tilt_codes or minimum_allocation is not None):
        raise ValueError(
            "sustainability preference must include an exclusion, tilt, or allocation bound"
        )
