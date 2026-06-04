from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.currency_codes import normalize_optional_currency_code
from pydantic import BaseModel, ConfigDict, Field, condecimal, field_validator, model_validator


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
    withholding_tax_rate: condecimal(ge=Decimal(0), le=Decimal(1)) | None = Field(
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
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        if self.tax_status == "UNKNOWN" and (
            self.withholding_tax_rate is not None
            or self.capital_gains_tax_applicable
            or self.income_tax_applicable
            or self.treaty_codes
        ):
            raise ValueError("UNKNOWN tax_status cannot carry applicable tax detail")
        return self

    model_config = ConfigDict()


def _validate_tax_rule_effective_window(
    *,
    effective_from: date,
    effective_to: date | None,
) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to must be on or after effective_from")


def _validate_tax_rule_threshold_pair(
    *,
    threshold_amount: Decimal | None,
    threshold_currency: str | None,
) -> None:
    if threshold_amount is not None and not threshold_currency:
        raise ValueError("threshold_currency is required when threshold_amount is supplied")
    if threshold_currency and threshold_amount is None:
        raise ValueError("threshold_amount is required when threshold_currency is supplied")


def _validate_tax_rule_evidence(
    *,
    applies_to_asset_classes: list[str],
    applies_to_security_ids: list[str],
    applies_to_income_types: list[str],
    rate: Decimal | None,
    threshold_amount: Decimal | None,
) -> None:
    if (
        applies_to_asset_classes
        or applies_to_security_ids
        or applies_to_income_types
        or rate is not None
        or threshold_amount is not None
    ):
        return
    raise ValueError("tax rule set records must carry bounded rule evidence")


class ClientTaxRuleSetRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the tax rule set.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the tax rule set.")
    mandate_id: str | None = Field(
        None, description="Mandate identifier when the rule is mandate-specific."
    )
    rule_set_id: str = Field(..., description="Source-owned tax rule-set identifier.")
    tax_year: int = Field(..., ge=1900, le=2100, description="Tax year for the rule reference.")
    jurisdiction_code: str = Field(..., description="Tax jurisdiction code for the rule.")
    rule_code: str = Field(..., description="Machine-readable tax rule code.")
    rule_category: Literal[
        "WITHHOLDING", "CAPITAL_GAINS", "INCOME", "TRANSACTION_TAX", "REPORTING", "OTHER"
    ] = Field(..., description="Bounded tax rule category.")
    rule_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Rule lifecycle status."
    )
    rule_source: str = Field(..., description="Source channel that published the rule.")
    applies_to_asset_classes: list[str] = Field(default_factory=list)
    applies_to_security_ids: list[str] = Field(default_factory=list)
    applies_to_income_types: list[str] = Field(default_factory=list)
    rate: condecimal(ge=Decimal(0), le=Decimal(1)) | None = Field(None)
    threshold_amount: condecimal(ge=Decimal(0)) | None = Field(None)
    threshold_currency: str | None = Field(
        None,
        description=(
            "Canonical three-letter currency for the threshold amount when the tax rule "
            "contains monetary threshold evidence."
        ),
    )
    effective_from: date = Field(..., description="Tax rule effective start date.")
    effective_to: date | None = Field(None, description="Tax rule effective end date.")
    rule_version: int = Field(1, ge=1)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @field_validator("threshold_currency", mode="before")
    @classmethod
    def _normalize_threshold_currency(cls, value: object) -> str | None:
        return normalize_optional_currency_code(value)

    @model_validator(mode="after")
    def validate_rule(self) -> "ClientTaxRuleSetRecord":
        _validate_tax_rule_effective_window(
            effective_from=self.effective_from,
            effective_to=self.effective_to,
        )
        _validate_tax_rule_threshold_pair(
            threshold_amount=self.threshold_amount,
            threshold_currency=self.threshold_currency,
        )
        _validate_tax_rule_evidence(
            applies_to_asset_classes=self.applies_to_asset_classes,
            applies_to_security_ids=self.applies_to_security_ids,
            applies_to_income_types=self.applies_to_income_types,
            rate=self.rate,
            threshold_amount=self.threshold_amount,
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


class ClientTaxRuleSetIngestionRequest(BaseModel):
    tax_rule_sets: list[ClientTaxRuleSetRecord] = Field(
        ...,
        description="Effective-dated client tax rule-set records to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_rule_uniqueness(self) -> "ClientTaxRuleSetIngestionRequest":
        keys = [
            (
                rule.client_id,
                rule.portfolio_id,
                rule.rule_set_id,
                rule.jurisdiction_code,
                rule.rule_code,
                rule.effective_from,
                rule.rule_version,
            )
            for rule in self.tax_rule_sets
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("tax_rule_sets contains duplicate effective records")
        return self

    model_config = ConfigDict()
