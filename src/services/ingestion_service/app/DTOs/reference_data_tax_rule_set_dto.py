from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, cast

from portfolio_common.currency_codes import normalize_optional_currency_code
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .ingestion_validation_errors import (
    INVALID_THRESHOLD_PAIR,
    MISSING_RULE_EVIDENCE,
    raise_ingestion_validation_error,
    validate_effective_window,
    validate_unique_records,
)

NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal(0))]
RatioDecimal = Annotated[Decimal, Field(ge=Decimal(0), le=Decimal(1))]


def _validate_tax_rule_effective_window(
    *,
    effective_from: date,
    effective_to: date | None,
) -> None:
    validate_effective_window(effective_from=effective_from, effective_to=effective_to)


def _validate_tax_rule_threshold_pair(
    *,
    threshold_amount: Decimal | None,
    threshold_currency: str | None,
) -> None:
    if threshold_amount is not None and not threshold_currency:
        raise_ingestion_validation_error(
            INVALID_THRESHOLD_PAIR,
            field_path="threshold_currency",
            message="threshold_currency is required when threshold_amount is supplied",
        )
    if threshold_currency and threshold_amount is None:
        raise_ingestion_validation_error(
            INVALID_THRESHOLD_PAIR,
            field_path="threshold_amount",
            message="threshold_amount is required when threshold_currency is supplied",
        )


def _tax_rule_has_bounded_evidence(
    *,
    applies_to_asset_classes: list[str],
    applies_to_security_ids: list[str],
    applies_to_income_types: list[str],
    rate: Decimal | None,
    threshold_amount: Decimal | None,
) -> bool:
    return any(
        (
            applies_to_asset_classes,
            applies_to_security_ids,
            applies_to_income_types,
            rate is not None,
            threshold_amount is not None,
        )
    )


def _validate_tax_rule_evidence(
    *,
    applies_to_asset_classes: list[str],
    applies_to_security_ids: list[str],
    applies_to_income_types: list[str],
    rate: Decimal | None,
    threshold_amount: Decimal | None,
) -> None:
    if _tax_rule_has_bounded_evidence(
        applies_to_asset_classes=applies_to_asset_classes,
        applies_to_security_ids=applies_to_security_ids,
        applies_to_income_types=applies_to_income_types,
        rate=rate,
        threshold_amount=threshold_amount,
    ):
        return
    raise_ingestion_validation_error(
        MISSING_RULE_EVIDENCE,
        field_path="tax_rule_sets",
        message="tax rule set records must carry bounded rule evidence",
    )


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
    rate: RatioDecimal | None = Field(None)
    threshold_amount: NonNegativeDecimal | None = Field(None)
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
        return cast(str | None, normalize_optional_currency_code(value))

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
        validate_unique_records(
            keys,
            field_path="tax_rule_sets",
            message="tax_rule_sets contains duplicate effective records",
        )
        return self

    model_config = ConfigDict()
