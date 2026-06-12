from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RatioDecimal = Annotated[Decimal, Field(ge=Decimal(0), le=Decimal(1))]


def _validate_tax_profile_effective_window(
    *,
    effective_from: date,
    effective_to: date | None,
) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to must be on or after effective_from")


def _validate_unknown_tax_status_detail(
    *,
    tax_status: str,
    withholding_tax_rate: Decimal | None,
    capital_gains_tax_applicable: bool,
    income_tax_applicable: bool,
    treaty_codes: list[str],
) -> None:
    has_tax_detail = (
        withholding_tax_rate is not None
        or capital_gains_tax_applicable
        or income_tax_applicable
        or treaty_codes
    )
    if tax_status == "UNKNOWN" and has_tax_detail:
        raise ValueError("UNKNOWN tax_status cannot carry applicable tax detail")


class ClientTaxProfileRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the tax profile.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the tax profile.")
    mandate_id: str | None = Field(
        None, description="Mandate identifier when the profile is mandate-specific."
    )
    tax_profile_id: str = Field(..., description="Source-owned tax profile identifier.")
    tax_residency_country: str = Field(
        ..., description="Client tax-residency country from the source system."
    )
    booking_tax_jurisdiction: str = Field(
        ..., description="Booking-center tax jurisdiction from the source system."
    )
    tax_status: Literal["TAXABLE", "TAX_EXEMPT", "WITHHOLDING_EXEMPT", "UNKNOWN"] = Field(
        ..., description="Bounded tax status from the source system."
    )
    profile_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Tax profile lifecycle status."
    )
    withholding_tax_rate: RatioDecimal | None = Field(
        None, description="Reference withholding rate ratio when supplied by the source."
    )
    capital_gains_tax_applicable: bool = Field(False)
    income_tax_applicable: bool = Field(False)
    treaty_codes: list[str] = Field(default_factory=list)
    eligible_account_types: list[str] = Field(default_factory=list)
    effective_from: date = Field(..., description="Tax profile effective start date.")
    effective_to: date | None = Field(None, description="Tax profile effective end date.")
    profile_version: int = Field(1, ge=1)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @model_validator(mode="after")
    def validate_profile(self) -> "ClientTaxProfileRecord":
        _validate_tax_profile_effective_window(
            effective_from=self.effective_from,
            effective_to=self.effective_to,
        )
        _validate_unknown_tax_status_detail(
            tax_status=self.tax_status,
            withholding_tax_rate=self.withholding_tax_rate,
            capital_gains_tax_applicable=self.capital_gains_tax_applicable,
            income_tax_applicable=self.income_tax_applicable,
            treaty_codes=self.treaty_codes,
        )
        return self

    model_config = ConfigDict()


class ClientTaxProfileIngestionRequest(BaseModel):
    tax_profiles: list[ClientTaxProfileRecord] = Field(
        ...,
        description="Effective-dated client tax profile records to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_profile_uniqueness(self) -> "ClientTaxProfileIngestionRequest":
        keys = [
            (
                profile.client_id,
                profile.portfolio_id,
                profile.tax_profile_id,
                profile.effective_from,
                profile.profile_version,
            )
            for profile in self.tax_profiles
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("tax_profiles contains duplicate effective records")
        return self

    model_config = ConfigDict()
