"""API contracts for the effective client tax-rule source product."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class ClientTaxRuleSetRequest(BaseModel):
    """Select effective tax-reference rules for one portfolio and date."""

    as_of_date: date = Field(
        ...,
        description="Business date used to resolve effective client tax rule-set records.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and policy-scoped consumers.",
        examples=["default"],
    )
    mandate_id: str | None = Field(
        None,
        description="Optional mandate identifier used to disambiguate portfolio tax rules.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    include_inactive_rules: bool = Field(
        False, description="When false, excludes inactive or expired tax rule records."
    )
    model_config = ConfigDict()


class ClientTaxRuleSetEntry(BaseModel):
    """One effective client tax-reference rule."""

    rule_set_id: str = Field(..., description="Source-owned tax rule-set identifier.")
    tax_year: int = Field(..., description="Tax year for the rule reference.")
    jurisdiction_code: str = Field(..., description="Tax jurisdiction code for the rule.")
    rule_code: str = Field(..., description="Machine-readable tax rule code.")
    rule_category: str = Field(..., description="Bounded tax rule category.")
    rule_status: str = Field(..., description="Tax rule lifecycle status.")
    rule_source: str = Field(..., description="Source channel that published the rule.")
    applies_to_asset_classes: list[str] = Field(default_factory=list)
    applies_to_security_ids: list[str] = Field(default_factory=list)
    applies_to_income_types: list[str] = Field(default_factory=list)
    rate: Decimal | None = Field(None, description="Reference rate ratio when supplied.")
    threshold_amount: Decimal | None = Field(None, description="Reference threshold amount.")
    threshold_currency: str | None = Field(None, description="Currency for threshold_amount.")
    effective_from: date = Field(..., description="Tax rule effective start date.")
    effective_to: date | None = Field(None, description="Tax rule effective end date.")
    rule_version: int = Field(..., description="Selected rule version.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")
    model_config = ConfigDict()


class ClientTaxRuleSetSupportability(BaseModel):
    """Operational readiness of the resolved tax-rule evidence."""

    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using client tax rule sets as DPM evidence.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["CLIENT_TAX_RULE_SET_READY"],
    )
    rule_count: int = Field(..., ge=0, description="Number of effective tax rules returned.")
    missing_data_families: list[str] = Field(default_factory=list)
    model_config = ConfigDict()


class ClientTaxRuleSetResponse(SourceDataProductRuntimeMetadata):
    """Effective tax-rule source product with lineage and supportability."""

    product_name: Literal["ClientTaxRuleSet"] = product_name_field("ClientTaxRuleSet")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the rule set.")
    client_id: str = Field(..., description="Client identifier bound to the rule set.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for rule resolution.")
    rules: list[ClientTaxRuleSetEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective client tax rule records.",
    )
    supportability: ClientTaxRuleSetSupportability = Field(
        ..., description="Supportability posture for tax-rule reference evidence."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict, description="Source lineage for tax rule-set resolution."
    )
    model_config = ConfigDict()
