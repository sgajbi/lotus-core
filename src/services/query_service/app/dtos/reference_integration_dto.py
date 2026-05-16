from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .source_data_product_identity import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)


class IntegrationWindow(BaseModel):
    start_date: date = Field(
        ...,
        description="Window start date for series retrieval (inclusive).",
        examples=["2026-01-01"],
    )
    end_date: date = Field(
        ...,
        description="Window end date for series retrieval (inclusive).",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()


class IntegrationPolicyContext(BaseModel):
    tenant_id: str | None = Field(
        None,
        description="Tenant identifier for policy-scoped data resolution.",
        examples=["tenant_sg_pb"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier used for deterministic assignment resolution.",
        examples=["policy_pack_wm_v1"],
    )

    model_config = ConfigDict()


class PortfolioManagerBookMembershipRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve active portfolio membership in the PM book.",
        examples=["2026-05-03"],
    )
    booking_center_code: str | None = Field(
        None,
        description="Optional booking-center filter for regional PM-book resolution.",
        examples=["Singapore"],
    )
    portfolio_types: list[str] = Field(
        default_factory=lambda: ["DISCRETIONARY"],
        description=(
            "Portfolio type allow-list for the book membership. The default keeps the first-wave "
            "DPM cohort scoped to discretionary mandates."
        ),
        examples=[["DISCRETIONARY"]],
    )
    include_inactive: bool = Field(
        False,
        description=(
            "When false, excludes closed or non-active portfolio records as of the requested "
            "business date."
        ),
    )

    model_config = ConfigDict()


class PortfolioManagerBookMember(BaseModel):
    portfolio_id: str = Field(
        ...,
        description="Portfolio in the source-owned PM book membership.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    )
    client_id: str = Field(
        ...,
        description="Client grouping identifier carried by the core portfolio master.",
        examples=["CIF_SG_GLOBAL_BAL_001"],
    )
    booking_center_code: str = Field(
        ...,
        description="Booking center owning the portfolio.",
        examples=["Singapore"],
    )
    portfolio_type: str = Field(
        ...,
        description="Portfolio product/type classification from the core portfolio master.",
        examples=["DISCRETIONARY"],
    )
    status: str = Field(
        ...,
        description="Portfolio lifecycle status from the core portfolio master.",
        examples=["ACTIVE"],
    )
    open_date: date = Field(
        ...,
        description="Portfolio open date used in active-membership resolution.",
        examples=["2025-03-31"],
    )
    close_date: date | None = Field(
        None,
        description="Portfolio close date, if any.",
        examples=["2026-12-31"],
    )
    base_currency: str = Field(
        ...,
        description="Portfolio base currency.",
        examples=["USD"],
    )
    source_record_id: str = Field(
        ...,
        description="Source record identifier for membership lineage.",
        examples=["portfolio:PB_SG_GLOBAL_BAL_001"],
    )

    model_config = ConfigDict()


class PortfolioManagerBookMembershipSupportability(BaseModel):
    state: Literal["READY", "INCOMPLETE"] = Field(
        ...,
        description="Supportability state for the resolved PM-book membership.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Machine-readable supportability reason.",
        examples=["PM_BOOK_MEMBERSHIP_READY"],
    )
    returned_portfolio_count: int = Field(
        ...,
        ge=0,
        description="Number of portfolio memberships returned.",
        examples=[1],
    )
    filters_applied: list[str] = Field(
        default_factory=list,
        description="Filters applied by the source product.",
        examples=[["portfolio_manager_id", "as_of_date", "portfolio_types"]],
    )

    model_config = ConfigDict()


class PortfolioManagerBookMembershipResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioManagerBookMembership"] = product_name_field(
        "PortfolioManagerBookMembership"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_manager_id: str = Field(
        ...,
        description=(
            "Portfolio-manager or relationship-manager identifier. First-wave lotus-core "
            "resolution is backed by the portfolio master `advisor_id` field."
        ),
        examples=["PM_SG_DPM_001"],
    )
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve membership.",
        examples=["2026-05-03"],
    )
    booking_center_code: str | None = Field(
        None,
        description="Booking-center filter used for the response, if supplied.",
        examples=["Singapore"],
    )
    members: list[PortfolioManagerBookMember] = Field(
        default_factory=list,
        description="Deterministically ordered source-owned portfolio memberships.",
    )
    supportability: PortfolioManagerBookMembershipSupportability = Field(
        ...,
        description="Supportability posture for automatic PM-book cohort discovery.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for the PM-book membership resolution.",
        examples=[
            {
                "source_system": "lotus-core",
                "source_field": "portfolios.advisor_id",
                "contract_version": "rfc_041_pm_book_membership_v1",
            }
        ],
    )

    model_config = ConfigDict()


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
        None,
        description="Policy pack associated with the mandate binding, when available.",
    )
    risk_profile: str = Field(..., description="Mandate risk profile.")
    effective_from: date = Field(..., description="Binding effective start date.")
    effective_to: date | None = Field(
        None,
        description="Binding effective end date, null when open-ended.",
    )
    binding_version: int = Field(..., description="Selected binding version.")
    source_record_id: str | None = Field(
        None,
        description="Source record id for mandate-cohort audit and replay.",
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
        ...,
        ge=0,
        description="Number of affected mandate bindings returned.",
        examples=[1],
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
        None,
        description="Timestamp when the selected model version was approved, if available.",
    )
    effective_from: date = Field(
        ...,
        description="Selected model version effective start date.",
        examples=["2026-05-01"],
    )
    effective_to: date | None = Field(
        None,
        description="Selected model version effective end date, null when open-ended.",
    )
    affected_mandates: list[CioModelChangeAffectedMandate] = Field(
        default_factory=list,
        description="Deterministically ordered affected discretionary mandates.",
    )
    supportability: CioModelChangeAffectedCohortSupportability = Field(
        ...,
        description="Readiness posture for automatic CIO model-change wave discovery.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for model definition and mandate binding discovery.",
    )

    model_config = ConfigDict()


class ClientRestrictionProfileRequest(BaseModel):
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


class SustainabilityPreferenceProfileRequest(BaseModel):
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
        default_factory=list,
        description="Asset classes in scope for the preference.",
    )
    exclusion_codes: list[str] = Field(
        default_factory=list,
        description="Sustainability exclusion codes in scope.",
    )
    positive_tilt_codes: list[str] = Field(
        default_factory=list,
        description="Positive sustainability tilt codes in scope.",
    )
    effective_from: date = Field(..., description="Preference effective start date.")
    effective_to: date | None = Field(None, description="Preference effective end date.")
    preference_version: int = Field(..., description="Selected preference profile version.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")

    model_config = ConfigDict()


class SustainabilityPreferenceProfileSupportability(BaseModel):
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
        default_factory=list,
        description="Missing source families that block profile consumption.",
    )

    model_config = ConfigDict()


class SustainabilityPreferenceProfileResponse(SourceDataProductRuntimeMetadata):
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


class ClientTaxProfileRequest(BaseModel):
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
        False,
        description="When false, excludes inactive or expired tax profile records.",
    )

    model_config = ConfigDict()


class ClientTaxProfileEntry(BaseModel):
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
        default_factory=dict,
        description="Source lineage for tax profile resolution.",
    )

    model_config = ConfigDict()


class ClientTaxRuleSetRequest(BaseModel):
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
        False,
        description="When false, excludes inactive or expired tax rule records.",
    )

    model_config = ConfigDict()


class ClientTaxRuleSetEntry(BaseModel):
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
        default_factory=dict,
        description="Source lineage for tax rule-set resolution.",
    )

    model_config = ConfigDict()


class ClientIncomeNeedsScheduleRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve active client income-needs schedules.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    include_inactive_schedules: bool = Field(
        False, description="When false, excludes inactive income-needs schedules."
    )

    model_config = ConfigDict()


class ClientIncomeNeedsScheduleEntry(BaseModel):
    schedule_id: str = Field(..., description="Source-owned income-needs schedule identifier.")
    need_type: str = Field(..., description="Bounded income need type.")
    need_status: str = Field(..., description="Income-needs lifecycle status.")
    amount: Decimal = Field(..., description="Source-supplied income need amount.")
    currency: str = Field(..., description="Currency for amount.")
    frequency: str = Field(..., description="Income-needs cadence.")
    start_date: date = Field(..., description="Income-needs schedule start date.")
    end_date: date | None = Field(None, description="Income-needs schedule end date.")
    priority: int = Field(..., description="Source-supplied priority.")
    funding_policy: str | None = Field(None, description="Bank/source funding policy reference.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")

    model_config = ConfigDict()


class ClientIncomeNeedsScheduleSupportability(BaseModel):
    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using income-needs schedules as DPM evidence."
    )
    reason: str = Field(..., description="Machine-readable supportability reason.")
    schedule_count: int = Field(..., ge=0, description="Number of effective schedules returned.")
    missing_data_families: list[str] = Field(default_factory=list)

    model_config = ConfigDict()


class ClientIncomeNeedsScheduleResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ClientIncomeNeedsSchedule"] = product_name_field(
        "ClientIncomeNeedsSchedule"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the schedules.")
    client_id: str = Field(..., description="Client identifier bound to the schedules.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for schedule resolution.")
    schedules: list[ClientIncomeNeedsScheduleEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective client income-needs schedules.",
    )
    supportability: ClientIncomeNeedsScheduleSupportability = Field(
        ..., description="Supportability posture for income-needs evidence."
    )
    lineage: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict()


class LiquidityReserveRequirementRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used to resolve active liquidity reserve requirements.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    include_inactive_requirements: bool = Field(
        False, description="When false, excludes inactive liquidity reserve requirements."
    )

    model_config = ConfigDict()


class LiquidityReserveRequirementEntry(BaseModel):
    reserve_requirement_id: str = Field(..., description="Source-owned reserve requirement id.")
    reserve_type: str = Field(..., description="Bounded reserve requirement type.")
    reserve_status: str = Field(..., description="Reserve requirement lifecycle status.")
    required_amount: Decimal = Field(..., description="Required reserve amount.")
    currency: str = Field(..., description="Currency for required_amount.")
    horizon_days: int = Field(..., description="Reserve horizon in calendar days.")
    priority: int = Field(..., description="Source-supplied priority.")
    policy_source: str = Field(..., description="Source policy or bank reference.")
    effective_from: date = Field(..., description="Requirement effective start date.")
    effective_to: date | None = Field(None, description="Requirement effective end date.")
    requirement_version: int = Field(..., description="Selected requirement version.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")

    model_config = ConfigDict()


class LiquidityReserveRequirementSupportability(BaseModel):
    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using reserve requirements as DPM evidence."
    )
    reason: str = Field(..., description="Machine-readable supportability reason.")
    requirement_count: int = Field(
        ..., ge=0, description="Number of effective reserve requirements returned."
    )
    missing_data_families: list[str] = Field(default_factory=list)

    model_config = ConfigDict()


class LiquidityReserveRequirementResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["LiquidityReserveRequirement"] = product_name_field(
        "LiquidityReserveRequirement"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the requirements.")
    client_id: str = Field(..., description="Client identifier bound to the requirements.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for requirement resolution.")
    requirements: list[LiquidityReserveRequirementEntry] = Field(
        default_factory=list,
        description="Deterministically ordered effective liquidity reserve requirements.",
    )
    supportability: LiquidityReserveRequirementSupportability = Field(
        ..., description="Supportability posture for liquidity reserve evidence."
    )
    lineage: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict()


class PlannedWithdrawalScheduleRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used as the lower bound for planned withdrawal schedules.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    horizon_days: int = Field(365, ge=1, le=3660, description="Forward withdrawal horizon.")
    include_inactive_withdrawals: bool = Field(
        False, description="When false, excludes inactive planned withdrawal schedules."
    )

    model_config = ConfigDict()


class PlannedWithdrawalScheduleEntry(BaseModel):
    withdrawal_schedule_id: str = Field(..., description="Source-owned withdrawal schedule id.")
    withdrawal_type: str = Field(..., description="Bounded planned withdrawal type.")
    withdrawal_status: str = Field(..., description="Withdrawal lifecycle status.")
    amount: Decimal = Field(..., description="Source-supplied planned withdrawal amount.")
    currency: str = Field(..., description="Currency for amount.")
    scheduled_date: date = Field(..., description="Scheduled withdrawal date.")
    recurrence_frequency: str | None = Field(None, description="Optional recurrence cadence.")
    purpose_code: str | None = Field(None, description="Optional source purpose code.")
    source_record_id: str | None = Field(None, description="Source record id for audit replay.")

    model_config = ConfigDict()


class PlannedWithdrawalScheduleSupportability(BaseModel):
    state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using planned withdrawals as DPM evidence."
    )
    reason: str = Field(..., description="Machine-readable supportability reason.")
    withdrawal_count: int = Field(..., ge=0, description="Number of withdrawals returned.")
    missing_data_families: list[str] = Field(default_factory=list)

    model_config = ConfigDict()


class PlannedWithdrawalScheduleResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PlannedWithdrawalSchedule"] = product_name_field(
        "PlannedWithdrawalSchedule"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the schedules.")
    client_id: str = Field(..., description="Client identifier bound to the schedules.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    as_of_date: date = Field(..., description="Business date used for schedule resolution.")
    horizon_days: int = Field(..., description="Forward withdrawal horizon.")
    withdrawals: list[PlannedWithdrawalScheduleEntry] = Field(
        default_factory=list,
        description="Deterministically ordered planned withdrawals in the requested horizon.",
    )
    supportability: PlannedWithdrawalScheduleSupportability = Field(
        ..., description="Supportability posture for planned withdrawal evidence."
    )
    lineage: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict()


class ExternalCurrencyExposureRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Business date used to evaluate external treasury currency exposure availability."
        ),
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency supplied by the downstream DPM workflow.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description=(
            "Optional currency universe requested by the downstream workflow. The current "
            "source-owner posture remains unavailable until external treasury ingestion is "
            "certified."
        ),
        examples=[["EUR", "JPY"]],
    )

    model_config = ConfigDict()


class ExternalCurrencyExposureSupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external treasury currency exposure. The current Lotus "
            "Core runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"],
    )
    exposure_count: int = Field(
        0,
        ge=0,
        description="Number of external currency exposure rows returned.",
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="External treasury source-data families required before exposures can be used.",
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities explicitly blocked by unavailable exposure posture.",
    )

    model_config = ConfigDict()


class ExternalCurrencyExposureResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalCurrencyExposure"] = product_name_field(
        "ExternalCurrencyExposure"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the exposure posture.")
    client_id: str = Field(..., description="Client identifier bound to the portfolio mandate.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    reporting_currency: str | None = Field(
        None,
        description="Requested reporting currency echoed for downstream audit.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description="Requested currency universe echoed for downstream audit.",
    )
    exposures: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External treasury exposure rows. Empty while external treasury ingestion is not "
            "certified."
        ),
    )
    supportability: ExternalCurrencyExposureSupportability = Field(
        ..., description="Fail-closed supportability posture for external currency exposure."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage and non-claim posture for external currency exposure.",
    )

    model_config = ConfigDict()


class ExternalHedgeExecutionReadinessRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Business date used to evaluate external treasury source availability for hedge "
            "execution readiness."
        ),
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency supplied by the downstream DPM workflow.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description=(
            "Optional exposure currencies the downstream workflow wants treasury readiness "
            "checked for. The current source-owner posture remains unavailable until external "
            "treasury ingestion is certified."
        ),
        examples=[["EUR", "JPY"]],
    )

    model_config = ConfigDict()


class ExternalHedgeExecutionReadinessSupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external treasury hedge execution readiness. The current "
            "Lotus Core runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"],
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="External treasury source-data families required before readiness can be used.",
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description=(
            "Capabilities explicitly blocked by the unavailable posture. These are non-claims, "
            "not pending recommendations."
        ),
    )

    model_config = ConfigDict()


class ExternalHedgeExecutionReadinessResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalHedgeExecutionReadiness"] = product_name_field(
        "ExternalHedgeExecutionReadiness"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the readiness posture.")
    client_id: str = Field(..., description="Client identifier bound to the portfolio mandate.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    reporting_currency: str | None = Field(
        None,
        description="Requested reporting currency echoed for downstream audit.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description="Requested exposure currencies echoed for downstream audit.",
    )
    readiness_checks: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External treasury readiness checks. Empty while external treasury ingestion is not "
            "certified."
        ),
    )
    supportability: ExternalHedgeExecutionReadinessSupportability = Field(
        ..., description="Fail-closed supportability posture for external treasury readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage and non-claim posture for external treasury readiness.",
    )

    model_config = ConfigDict()


class BenchmarkAssignmentRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the active benchmark assignment.",
        examples=["2026-01-31"],
    )
    reporting_currency: str | None = Field(
        None,
        description=(
            "Optional downstream context currency for caller symmetry and lineage. "
            "This field does not change benchmark assignment selection in the current "
            "implementation."
        ),
        examples=["USD"],
    )
    policy_context: IntegrationPolicyContext | None = Field(
        None,
        description=(
            "Optional tenant/policy context reserved for governance metadata and future "
            "policy-bound resolution. The current implementation still resolves the "
            "effective assignment by portfolio_id and as_of_date."
        ),
    )

    model_config = ConfigDict()


class BenchmarkAssignmentResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["BenchmarkAssignment"] = product_name_field("BenchmarkAssignment")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ...,
        description="Canonical portfolio identifier.",
        examples=["DEMO_DPM_EUR_001"],
    )
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    as_of_date: date = Field(
        ...,
        description="As-of date used to resolve the assignment.",
        examples=["2026-01-31"],
    )
    effective_from: date = Field(
        ...,
        description="Assignment effective start date.",
        examples=["2025-01-01"],
    )
    effective_to: date | None = Field(
        None,
        description="Assignment effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    assignment_source: str = Field(
        ...,
        description="Source channel that established the assignment.",
        examples=["benchmark_policy_engine"],
    )
    assignment_status: str = Field(
        ...,
        description="Assignment lifecycle status.",
        examples=["active"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier associated with the assignment record.",
        examples=["policy_pack_wm_v1"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system identifier.",
        examples=["lotus-manage"],
    )
    assignment_recorded_at: datetime = Field(
        ...,
        description="Timestamp when assignment record was captured in lotus-core.",
        examples=["2026-01-31T09:15:00Z"],
    )
    assignment_version: int = Field(
        ...,
        description="Monotonic assignment version for effective-date ties.",
        examples=[3],
    )
    contract_version: str = Field(
        "rfc_062_v1",
        description="Query contract version for benchmark assignment integration.",
        examples=["rfc_062_v1"],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the approved model target version.",
        examples=["2026-03-25"],
    )
    include_inactive_targets: bool = Field(
        False,
        description=(
            "Include inactive target rows when true. Default false returns only active "
            "target rows suitable for DPM execution."
        ),
        examples=[False],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the effective mandate binding.",
        examples=["2026-04-10"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )
    mandate_id: str | None = Field(
        None,
        description="Optional mandate identifier to disambiguate the portfolio binding.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    booking_center_code: str | None = Field(
        None,
        description="Optional booking-center selector when downstream context already knows it.",
        examples=["Singapore"],
    )
    include_policy_pack: bool = Field(
        True,
        description="Return policy_pack_id when true. Default true is required by lotus-manage.",
        examples=[True],
    )

    model_config = ConfigDict()


class RebalanceBandContext(BaseModel):
    default_band: Decimal = Field(
        ...,
        description="Default instrument rebalance band as a decimal ratio.",
        examples=["0.0250000000"],
    )
    cash_reserve_weight: Decimal | None = Field(
        None,
        description="Optional target cash reserve weight as a decimal ratio.",
        examples=["0.0200000000"],
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using this binding in stateful DPM.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code explaining mandate binding readiness.",
        examples=["MANDATE_BINDING_READY"],
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="Missing source families that block or degrade stateful DPM source assembly.",
        examples=[[]],
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DiscretionaryMandateBinding"] = product_name_field(
        "DiscretionaryMandateBinding"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    mandate_id: str = Field(
        ...,
        description="Canonical discretionary mandate identifier.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    client_id: str = Field(
        ...,
        description="Canonical client identifier bound to the mandate.",
        examples=["CIF_SG_000184"],
    )
    mandate_type: str = Field(
        ..., description="Mandate type resolved for this binding.", examples=["discretionary"]
    )
    discretionary_authority_status: str = Field(
        ...,
        description="Authority status used by lotus-manage to allow, degrade, or block DPM.",
        examples=["active"],
    )
    booking_center_code: str = Field(
        ..., description="Booking center governing the mandate.", examples=["Singapore"]
    )
    jurisdiction_code: str = Field(
        ..., description="Legal or regulatory jurisdiction code for the mandate.", examples=["SG"]
    )
    model_portfolio_id: str = Field(
        ...,
        description="Approved model portfolio identifier selected for this mandate.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier used for downstream DPM constraints.",
        examples=["POLICY_DPM_SG_BALANCED_V1"],
    )
    mandate_objective: str | None = Field(
        None,
        description=(
            "Source-owned discretionary mandate objective for digital-twin and mandate-health "
            "workflows. Null means no mandate administration source value was available."
        ),
        examples=["Preserve and grow global balanced wealth within controlled drawdown limits."],
    )
    risk_profile: str = Field(..., description="Mandate risk profile.", examples=["balanced"])
    investment_horizon: str = Field(
        ..., description="Mandate investment horizon classification.", examples=["long_term"]
    )
    review_cadence: str | None = Field(
        None,
        description="Source-owned mandate review cadence used for review-cycle health evidence.",
        examples=["quarterly"],
    )
    last_review_date: date | None = Field(
        None,
        description="Most recent completed discretionary mandate review date from source data.",
        examples=["2026-03-31"],
    )
    next_review_due_date: date | None = Field(
        None,
        description="Next due discretionary mandate review date from source data.",
        examples=["2026-06-30"],
    )
    leverage_allowed: bool = Field(
        ..., description="Whether leverage is permitted by the mandate.", examples=[False]
    )
    tax_awareness_allowed: bool = Field(
        ..., description="Whether tax-aware DPM execution is allowed.", examples=[True]
    )
    settlement_awareness_required: bool = Field(
        ..., description="Whether settlement-aware DPM execution is required.", examples=[True]
    )
    rebalance_frequency: str = Field(
        ..., description="Expected rebalance cadence.", examples=["monthly"]
    )
    rebalance_bands: RebalanceBandContext = Field(
        ..., description="Mandate-level rebalance bands and cash reserve policy."
    )
    effective_from: date = Field(
        ..., description="Resolved binding effective start date.", examples=["2026-04-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Resolved binding effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    binding_version: int = Field(
        ..., description="Binding version selected for deterministic tie-breaks.", examples=[1]
    )
    supportability: DiscretionaryMandateBindingSupportability = Field(
        ..., description="Readiness and completeness diagnostics for this mandate binding."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage metadata for audit, replay, and downstream diagnostics.",
        examples=[
            {
                "source_system": "mandate_admin",
                "source_record_id": "mandate_001_v1",
                "contract_version": "rfc_087_v1",
            }
        ],
    )

    model_config = ConfigDict()


class InstrumentEligibilityBulkRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve effective eligibility profiles.",
        examples=["2026-04-10"],
    )
    security_ids: list[str] = Field(
        ...,
        description=(
            "Canonical security identifiers to resolve in one deterministic batch. Request order "
            "is preserved and unknown securities are returned explicitly."
        ),
        min_length=1,
        examples=[["AAPL", "MSFT", "PRIVCREDIT-A"]],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )
    include_restricted_rationale: bool = Field(
        False,
        description=(
            "Reserved operator/audit flag. The public DPM source product returns bounded "
            "restriction_reason_codes and never exposes sensitive free-text rationale."
        ),
        examples=[False],
    )

    model_config = ConfigDict()


class InstrumentEligibilityRecord(BaseModel):
    security_id: str = Field(..., description="Canonical security identifier.", examples=["AAPL"])
    found: bool = Field(
        ...,
        description="Whether an effective eligibility profile was found for this security.",
        examples=[True],
    )
    eligibility_status: Literal["APPROVED", "RESTRICTED", "SELL_ONLY", "BANNED", "UNKNOWN"] = Field(
        ..., description="DPM eligibility status.", examples=["APPROVED"]
    )
    product_shelf_status: str = Field(
        ..., description="Product shelf status used by DPM execution.", examples=["APPROVED"]
    )
    buy_allowed: bool = Field(..., description="Whether DPM may buy this instrument.")
    sell_allowed: bool = Field(..., description="Whether DPM may sell this instrument.")
    restriction_reason_codes: list[str] = Field(
        default_factory=list,
        description="Bounded restriction codes suitable for downstream audit and explainability.",
        examples=[["PRIVATE_ASSET_REVIEW"]],
    )
    settlement_days: int | None = Field(
        None,
        description="Expected settlement cycle in business days; null when unknown.",
        examples=[2],
    )
    settlement_calendar_id: str | None = Field(
        None,
        description="Settlement calendar identifier; null when unknown.",
        examples=["US_NYSE"],
    )
    liquidity_tier: str | None = Field(None, description="Liquidity tier.", examples=["L1"])
    issuer_id: str | None = Field(None, description="Direct issuer identifier.", examples=["APPLE"])
    issuer_name: str | None = Field(
        None, description="Direct issuer name.", examples=["Apple Inc."]
    )
    ultimate_parent_issuer_id: str | None = Field(
        None, description="Ultimate parent issuer identifier.", examples=["APPLE_PARENT"]
    )
    ultimate_parent_issuer_name: str | None = Field(
        None, description="Ultimate parent issuer name.", examples=["Apple Inc."]
    )
    asset_class: str | None = Field(None, description="Asset class label.", examples=["Equity"])
    country_of_risk: str | None = Field(None, description="Country of risk.", examples=["US"])
    effective_from: date | None = Field(
        None, description="Resolved effective start date; null when unknown."
    )
    effective_to: date | None = Field(
        None, description="Resolved effective end date; null when open-ended or unknown."
    )
    quality_status: str = Field(
        ..., description="Source data quality status.", examples=["ACCEPTED"]
    )
    source_record_id: str | None = Field(
        None, description="Source record identifier for audit and replay."
    )

    model_config = ConfigDict()


class InstrumentEligibilitySupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using this eligibility batch in DPM.",
        examples=["READY"],
    )
    reason: str = Field(
        ..., description="Bounded reason code for eligibility readiness.", examples=["READY"]
    )
    requested_count: int = Field(..., description="Number of requested security identifiers.")
    resolved_count: int = Field(..., description="Number with effective eligibility profiles.")
    missing_security_ids: list[str] = Field(
        default_factory=list,
        description="Security identifiers with no effective eligibility profile.",
        examples=[["UNKNOWN_SEC"]],
    )

    model_config = ConfigDict()


class InstrumentEligibilityBulkResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["InstrumentEligibilityProfile"] = product_name_field(
        "InstrumentEligibilityProfile"
    )
    product_version: Literal["v1"] = product_version_field()
    records: list[InstrumentEligibilityRecord] = Field(
        ...,
        description="Eligibility records in the same order as request security_ids.",
    )
    supportability: InstrumentEligibilitySupportability = Field(
        ..., description="Batch-level DPM source-data readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and diagnostics.",
    )

    model_config = ConfigDict()


class PortfolioTaxLotPageRequest(BaseModel):
    page_size: int = Field(
        250,
        ge=1,
        le=1000,
        description="Maximum tax-lot records to return for this page.",
        examples=[250],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous portfolio tax-lot page.",
        examples=["eyJwIjp7Imxhc3RfbG90X2lkIjoiTE9ULTAwMSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class PortfolioTaxLotWindowRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used to resolve current tax-lot state.",
        examples=["2026-04-10"],
    )
    security_ids: list[str] | None = Field(
        None,
        description=(
            "Optional security filter. Omit to return tax lots for all securities in the portfolio "
            "window."
        ),
        examples=[["EQ_US_AAPL", "FI_US_TREASURY_10Y"]],
    )
    lot_status_filter: Literal["OPEN", "CLOSED"] | None = Field(
        None,
        description=(
            "Optional explicit lot status filter. When omitted, open lots are returned by default."
        ),
        examples=["OPEN"],
    )
    include_closed_lots: bool = Field(
        False,
        description="Whether to include closed lots when lot_status_filter is not explicitly set.",
        examples=[False],
    )
    page: PortfolioTaxLotPageRequest = Field(
        default_factory=PortfolioTaxLotPageRequest,
        description="Cursor pagination request for large tax-lot windows.",
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )

    @model_validator(mode="after")
    def validate_security_filter(self) -> "PortfolioTaxLotWindowRequest":
        if self.security_ids is not None:
            normalized = [security_id.strip() for security_id in self.security_ids]
            if any(not security_id for security_id in normalized):
                raise ValueError("security_ids must contain non-empty identifiers")
            if len(normalized) != len(set(normalized)):
                raise ValueError("security_ids must not contain duplicates")
            self.security_ids = normalized
        return self

    model_config = ConfigDict()


class PortfolioTaxLotRecord(BaseModel):
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    security_id: str = Field(
        ..., description="Canonical security identifier.", examples=["EQ_US_AAPL"]
    )
    instrument_id: str = Field(
        ..., description="Canonical instrument identifier.", examples=["EQ_US_AAPL"]
    )
    lot_id: str = Field(
        ..., description="Stable tax-lot identifier.", examples=["LOT-TXN-BUY-AAPL-001"]
    )
    open_quantity: Decimal = Field(
        ..., description="Current open lot quantity.", examples=["100.0000000000"]
    )
    original_quantity: Decimal = Field(
        ..., description="Original acquired lot quantity.", examples=["100.0000000000"]
    )
    acquisition_date: date = Field(
        ..., description="Lot acquisition date.", examples=["2026-03-25"]
    )
    cost_basis_base: Decimal = Field(
        ...,
        description="Current lot cost basis in portfolio base currency.",
        examples=["15005.5000000000"],
    )
    cost_basis_local: Decimal = Field(
        ...,
        description="Current lot cost basis in local trade currency.",
        examples=["15005.5000000000"],
    )
    local_currency: str | None = Field(
        None, description="Local trade currency for this lot.", examples=["USD"]
    )
    tax_lot_status: Literal["OPEN", "CLOSED"] = Field(
        ..., description="Current tax-lot status.", examples=["OPEN"]
    )
    source_transaction_id: str = Field(
        ...,
        description="Source BUY or transfer transaction identifier.",
        examples=["TXN-BUY-AAPL-001"],
    )
    source_lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lot-level lineage tying the row to source transaction and calculation policy.",
        examples=[
            {
                "source_system": "front_office_portfolio_seed",
                "calculation_policy_id": "BUY_DEFAULT_POLICY",
                "calculation_policy_version": "1.0.0",
            }
        ],
    )

    model_config = ConfigDict()


class PortfolioTaxLotWindowSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using tax lots in DPM.", examples=["READY"]
    )
    reason: str = Field(
        ..., description="Bounded reason code for tax-lot readiness.", examples=["TAX_LOTS_READY"]
    )
    requested_security_count: int | None = Field(
        None,
        description=(
            "Number of securities explicitly requested, null when the full portfolio was requested."
        ),
        examples=[2],
    )
    returned_lot_count: int = Field(
        ..., description="Number of tax lots returned in this page.", examples=[25]
    )
    missing_security_ids: list[str] = Field(
        default_factory=list,
        description="Requested securities with no lots in the resolved page scope.",
        examples=[["UNKNOWN_SEC"]],
    )

    model_config = ConfigDict()


class PortfolioTaxLotWindowResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["PortfolioTaxLotWindow"] = product_name_field("PortfolioTaxLotWindow")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    as_of_date: date = Field(
        ..., description="As-of date used for lot resolution.", examples=["2026-04-10"]
    )
    lots: list[PortfolioTaxLotRecord] = Field(
        default_factory=list,
        description="Paged portfolio-window tax lots ordered by acquisition date and lot id.",
    )
    page: ReferencePageMetadata = Field(
        ..., description="Cursor pagination metadata for this tax-lot page."
    )
    supportability: PortfolioTaxLotWindowSupportability = Field(
        ..., description="Batch-level DPM tax-lot source-data readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and diagnostics.",
        examples=[{"source_system": "position_lot_state", "contract_version": "rfc_087_v1"}],
    )

    model_config = ConfigDict()


class MarketDataCurrencyPair(BaseModel):
    from_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Source currency for an FX conversion pair.",
        examples=["USD"],
    )
    to_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Target currency for an FX conversion pair.",
        examples=["SGD"],
    )

    @model_validator(mode="after")
    def normalize_pair(self) -> "MarketDataCurrencyPair":
        self.from_currency = self.from_currency.strip().upper()
        self.to_currency = self.to_currency.strip().upper()
        if len(self.from_currency) != 3 or len(self.to_currency) != 3:
            raise ValueError("currency pair members must be ISO currency codes")
        if self.from_currency == self.to_currency:
            raise ValueError("currency pair members must be different")
        return self

    model_config = ConfigDict()


class TransactionCostCurvePageRequest(BaseModel):
    page_size: int = Field(
        250,
        ge=1,
        le=1000,
        description="Maximum observed cost-curve points to return in one response.",
        examples=[250],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous transaction-cost curve page.",
        examples=["eyJwIjp7Imxhc3Rfa2V5IjoiLi4uIn0sInMiOiIuLi4ifQ=="],
    )

    model_config = ConfigDict()


class TransactionCostCurveRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business as-of date used to bound observed transaction-cost evidence.",
        examples=["2026-05-03"],
    )
    window: IntegrationWindow = Field(
        ...,
        description="Inclusive transaction-date window used to derive observed cost points.",
    )
    security_ids: list[str] | None = Field(
        None,
        description="Optional security identifiers to restrict observed cost evidence.",
        examples=[["SEC-US-IBM", "SEC-US-AAPL"]],
    )
    transaction_types: list[str] | None = Field(
        None,
        description="Optional transaction types to restrict observed cost evidence.",
        examples=[["BUY", "SELL"]],
    )
    min_observation_count: int = Field(
        1,
        ge=1,
        le=100,
        description="Minimum observed transaction count required before a curve point is returned.",
        examples=[3],
    )
    page: TransactionCostCurvePageRequest = Field(
        default_factory=TransactionCostCurvePageRequest,
        description="Cursor paging request for observed transaction-cost curve points.",
    )
    tenant_id: str | None = Field(
        None,
        description=(
            "Tenant scope for future policy enforcement. Null until tenant partitioning is active."
        ),
        examples=["tenant_sg_pb"],
    )

    @model_validator(mode="after")
    def validate_filters(self) -> "TransactionCostCurveRequest":
        if self.window.end_date < self.window.start_date:
            raise ValueError("window.end_date must be on or after window.start_date")
        if self.security_ids is not None:
            normalized = [security_id.strip() for security_id in self.security_ids]
            if any(not security_id for security_id in normalized):
                raise ValueError("security_ids must not contain blank identifiers")
            if len(set(normalized)) != len(normalized):
                raise ValueError("security_ids must not contain duplicates")
            self.security_ids = normalized
        if self.transaction_types is not None:
            normalized_types = [
                transaction_type.strip().upper() for transaction_type in self.transaction_types
            ]
            if any(not transaction_type for transaction_type in normalized_types):
                raise ValueError("transaction_types must not contain blank values")
            if len(set(normalized_types)) != len(normalized_types):
                raise ValueError("transaction_types must not contain duplicates")
            self.transaction_types = normalized_types
        return self

    model_config = ConfigDict()


class TransactionCostCurvePoint(BaseModel):
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier for the observed curve point.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    )
    security_id: str = Field(
        ...,
        description="Security identifier represented by this point.",
        examples=["SEC-US-AAPL"],
    )
    transaction_type: str = Field(..., description="Observed transaction type.", examples=["BUY"])
    currency: str = Field(
        ...,
        description="Currency of the observed fee and notional values.",
        examples=["USD"],
    )
    observation_count: int = Field(
        ..., description="Number of transactions represented.", examples=[12]
    )
    total_notional: Decimal = Field(
        ...,
        description="Sum of absolute gross transaction notional.",
        examples=["250000.0000000000"],
    )
    total_cost: Decimal = Field(
        ...,
        description="Sum of observed transaction fees.",
        examples=["125.0000000000"],
    )
    average_cost_bps: Decimal = Field(
        ...,
        description="Observed average cost in basis points of notional, not a predictive quote.",
        examples=["5.0000"],
    )
    min_cost_bps: Decimal = Field(
        ...,
        description="Minimum observed transaction cost in bps.",
        examples=["4.7500"],
    )
    max_cost_bps: Decimal = Field(
        ...,
        description="Maximum observed transaction cost in bps.",
        examples=["5.2500"],
    )
    first_observed_date: date = Field(
        ...,
        description="Earliest transaction date in the point.",
        examples=["2026-04-01"],
    )
    last_observed_date: date = Field(
        ...,
        description="Latest transaction date in the point.",
        examples=["2026-05-03"],
    )
    sample_transaction_ids: list[str] = Field(
        default_factory=list,
        description="Bounded deterministic sample of source transaction identifiers.",
    )
    source_lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage for the observed transaction-cost evidence.",
        examples=[
            {
                "source_system": "transactions",
                "source_table": "transactions,transaction_costs",
                "contract_version": "rfc_040_wtbd_007_v1",
            }
        ],
    )

    model_config = ConfigDict()


class TransactionCostCurveSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for using observed cost evidence in DPM proof packs.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code for observed transaction-cost evidence readiness.",
        examples=["TRANSACTION_COST_CURVE_READY"],
    )
    requested_security_count: int | None = Field(
        None,
        description=(
            "Number of securities explicitly requested, null when all observed securities are "
            "allowed."
        ),
    )
    returned_curve_point_count: int = Field(
        ...,
        description="Number of observed transaction-cost curve points returned.",
        examples=[8],
    )
    missing_security_ids: list[str] = Field(
        default_factory=list,
        description="Requested securities with no returned qualifying cost evidence.",
    )

    model_config = ConfigDict()


class TransactionCostCurveResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["TransactionCostCurve"] = product_name_field("TransactionCostCurve")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    as_of_date: date = Field(
        ..., description="Business as-of date used for the curve.", examples=["2026-05-03"]
    )
    window: IntegrationWindow = Field(..., description="Transaction-date evidence window.")
    curve_points: list[TransactionCostCurvePoint] = Field(
        default_factory=list,
        description="Observed transaction-cost curve points derived from booked transaction fees.",
    )
    page: ReferencePageMetadata = Field(
        ..., description="Cursor pagination metadata for this cost-curve page."
    )
    supportability: TransactionCostCurveSupportability = Field(
        ..., description="Readiness posture for observed transaction-cost evidence."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Product-level source lineage for transaction-cost evidence.",
        examples=[
            {
                "source_system": "transactions",
                "contract_version": "rfc_040_wtbd_007_v1",
            }
        ],
    )

    model_config = ConfigDict()


class MarketDataCoverageRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used to resolve latest available price and FX observations.",
        examples=["2026-04-10"],
    )
    instrument_ids: list[str] = Field(
        default_factory=list,
        description="Held and target instrument identifiers requiring latest price coverage.",
        examples=[["EQ_US_AAPL", "FI_US_TREASURY_10Y"]],
    )
    currency_pairs: list[MarketDataCurrencyPair] = Field(
        default_factory=list,
        description="FX conversion pairs required for valuation and rebalance sizing.",
        examples=[[{"from_currency": "USD", "to_currency": "SGD"}]],
    )
    valuation_currency: str | None = Field(
        None,
        min_length=3,
        max_length=3,
        description="Optional target valuation currency used for supportability lineage.",
        examples=["SGD"],
    )
    max_staleness_days: int = Field(
        5,
        ge=0,
        le=31,
        description=(
            "Maximum acceptable age in calendar days before an observation is marked stale."
        ),
        examples=[5],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )

    @model_validator(mode="after")
    def validate_request(self) -> "MarketDataCoverageRequest":
        normalized_instruments = [instrument_id.strip() for instrument_id in self.instrument_ids]
        if any(not instrument_id for instrument_id in normalized_instruments):
            raise ValueError("instrument_ids must contain non-empty identifiers")
        if len(normalized_instruments) != len(set(normalized_instruments)):
            raise ValueError("instrument_ids must not contain duplicates")
        normalized_pairs = [(pair.from_currency, pair.to_currency) for pair in self.currency_pairs]
        if len(normalized_pairs) != len(set(normalized_pairs)):
            raise ValueError("currency_pairs must not contain duplicates")
        self.instrument_ids = normalized_instruments
        if self.valuation_currency is not None:
            self.valuation_currency = self.valuation_currency.strip().upper()
        return self

    model_config = ConfigDict()


class MarketDataPriceCoverageRecord(BaseModel):
    instrument_id: str = Field(
        ..., description="Requested instrument identifier.", examples=["EQ_US_AAPL"]
    )
    found: bool = Field(
        ..., description="Whether core found a price observation on or before as_of_date."
    )
    price_date: date | None = Field(
        None, description="Resolved price observation date.", examples=["2026-04-10"]
    )
    price: Decimal | None = Field(
        None, description="Resolved price value when available.", examples=["187.1200000000"]
    )
    currency: str | None = Field(
        None, description="Price currency when available.", examples=["USD"]
    )
    age_days: int | None = Field(
        None, description="Calendar age of the resolved price observation.", examples=[0]
    )
    quality_status: Literal["READY", "STALE", "MISSING"] = Field(
        ..., description="Price coverage status for this instrument.", examples=["READY"]
    )

    model_config = ConfigDict()


class MarketDataFxCoverageRecord(BaseModel):
    from_currency: str = Field(..., description="Source currency.", examples=["USD"])
    to_currency: str = Field(..., description="Target currency.", examples=["SGD"])
    found: bool = Field(
        ..., description="Whether core found an FX observation on or before as_of_date."
    )
    rate_date: date | None = Field(
        None, description="Resolved FX observation date.", examples=["2026-04-10"]
    )
    rate: Decimal | None = Field(
        None, description="Resolved FX conversion rate.", examples=["1.3521000000"]
    )
    age_days: int | None = Field(
        None, description="Calendar age of the resolved FX observation.", examples=[0]
    )
    quality_status: Literal["READY", "STALE", "MISSING"] = Field(
        ..., description="FX coverage status for this pair.", examples=["READY"]
    )

    model_config = ConfigDict()


class MarketDataCoverageSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ..., description="Supportability state for using market data in DPM.", examples=["READY"]
    )
    reason: str = Field(
        ...,
        description="Bounded reason code for market-data readiness.",
        examples=["MARKET_DATA_READY"],
    )
    requested_price_count: int = Field(
        ..., description="Number of requested instrument price observations.", examples=[2]
    )
    resolved_price_count: int = Field(
        ..., description="Number of requested instruments with a resolved price.", examples=[2]
    )
    requested_fx_count: int = Field(
        ..., description="Number of requested FX conversion pairs.", examples=[1]
    )
    resolved_fx_count: int = Field(
        ..., description="Number of requested FX pairs with a resolved rate.", examples=[1]
    )
    missing_instrument_ids: list[str] = Field(
        default_factory=list,
        description="Requested instruments without a price observation.",
        examples=[["UNKNOWN_SEC"]],
    )
    stale_instrument_ids: list[str] = Field(
        default_factory=list,
        description="Requested instruments whose latest price is older than max_staleness_days.",
        examples=[["EQ_US_AAPL"]],
    )
    missing_currency_pairs: list[str] = Field(
        default_factory=list,
        description="Requested FX pairs without a rate observation.",
        examples=[["USD/SGD"]],
    )
    stale_currency_pairs: list[str] = Field(
        default_factory=list,
        description="Requested FX pairs whose latest rate is older than max_staleness_days.",
        examples=[["USD/SGD"]],
    )

    model_config = ConfigDict()


class MarketDataCoverageWindowResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["MarketDataCoverageWindow"] = product_name_field(
        "MarketDataCoverageWindow"
    )
    product_version: Literal["v1"] = product_version_field()
    as_of_date: date = Field(
        ..., description="As-of date used for market-data resolution.", examples=["2026-04-10"]
    )
    valuation_currency: str | None = Field(
        None, description="Requested valuation currency context.", examples=["SGD"]
    )
    price_coverage: list[MarketDataPriceCoverageRecord] = Field(
        default_factory=list,
        description="Coverage records for requested instrument prices.",
    )
    fx_coverage: list[MarketDataFxCoverageRecord] = Field(
        default_factory=list,
        description="Coverage records for requested FX pairs.",
    )
    supportability: MarketDataCoverageSupportability = Field(
        ..., description="Batch-level DPM market-data readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and diagnostics.",
        examples=[
            {
                "source_system": "market_prices+fx_rates",
                "contract_version": "rfc_087_v1",
            }
        ],
    )

    model_config = ConfigDict()


DpmSourceFamilyState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]


class DpmSourceReadinessRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used to evaluate DPM source-family readiness.",
        examples=["2026-04-10"],
    )
    tenant_id: str | None = Field(
        None,
        description="Optional tenant identifier carried for lineage and future policy resolution.",
        examples=["tenant_sg_pb"],
    )
    mandate_id: str | None = Field(
        None,
        description="Optional mandate identifier to disambiguate the portfolio binding.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    model_portfolio_id: str | None = Field(
        None,
        description=(
            "Optional model portfolio identifier. When omitted, readiness uses the model "
            "portfolio resolved from the mandate binding."
        ),
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    instrument_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional held or caller-known instrument identifiers. Readiness unions these with "
            "model target instruments before checking eligibility, tax lots, and market data."
        ),
        examples=[["FO_EQ_AAPL_US", "FO_BOND_UST_2030"]],
    )
    currency_pairs: list[MarketDataCurrencyPair] = Field(
        default_factory=list,
        description="FX conversion pairs required for stateful DPM source assembly.",
        examples=[[{"from_currency": "EUR", "to_currency": "USD"}]],
    )
    valuation_currency: str | None = Field(
        None,
        min_length=3,
        max_length=3,
        description="Optional target valuation currency used for market-data supportability.",
        examples=["USD"],
    )
    max_staleness_days: int = Field(
        5,
        ge=0,
        le=31,
        description="Maximum acceptable market-data age before a price or FX rate is stale.",
        examples=[5],
    )

    @model_validator(mode="after")
    def normalize_request(self) -> "DpmSourceReadinessRequest":
        normalized_instruments = [instrument_id.strip() for instrument_id in self.instrument_ids]
        if any(not instrument_id for instrument_id in normalized_instruments):
            raise ValueError("instrument_ids must contain non-empty identifiers")
        if len(normalized_instruments) != len(set(normalized_instruments)):
            raise ValueError("instrument_ids must not contain duplicates")
        self.instrument_ids = normalized_instruments
        if self.valuation_currency is not None:
            self.valuation_currency = self.valuation_currency.strip().upper()
        return self

    model_config = ConfigDict()


class DpmSourceFamilyReadiness(BaseModel):
    family: Literal["mandate", "model_targets", "eligibility", "tax_lots", "market_data"] = Field(
        ...,
        description="DPM source family represented by this readiness row.",
        examples=["market_data"],
    )
    product_name: str = Field(
        ...,
        description="Core source-data product used to evaluate this family.",
        examples=["MarketDataCoverageWindow"],
    )
    state: DpmSourceFamilyState = Field(
        ...,
        description="Readiness state for this source family.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code explaining the source-family state.",
        examples=["MARKET_DATA_READY"],
    )
    missing_items: list[str] = Field(
        default_factory=list,
        description=(
            "Bounded missing source items such as securities, FX pairs, or source families."
        ),
        examples=[["UNKNOWN_SEC"]],
    )
    stale_items: list[str] = Field(
        default_factory=list,
        description="Bounded stale source items such as prices or FX pairs older than policy.",
        examples=[["FO_EQ_SAP_DE"]],
    )
    evidence_count: int = Field(
        0,
        ge=0,
        description="Count of records or observations supporting this readiness row.",
        examples=[9],
    )

    model_config = ConfigDict()


class DpmSourceReadinessSupportability(BaseModel):
    state: DpmSourceFamilyState = Field(
        ...,
        description="Overall readiness state for promoting stateful DPM source assembly.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code for the overall source-family readiness decision.",
        examples=["DPM_SOURCE_READINESS_READY"],
    )
    ready_family_count: int = Field(
        ..., description="Number of source families in READY state.", examples=[5]
    )
    degraded_family_count: int = Field(
        ..., description="Number of source families in DEGRADED state.", examples=[0]
    )
    incomplete_family_count: int = Field(
        ..., description="Number of source families in INCOMPLETE state.", examples=[0]
    )
    unavailable_family_count: int = Field(
        ..., description="Number of source families in UNAVAILABLE state.", examples=[0]
    )

    model_config = ConfigDict()


class DpmSourceReadinessResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DpmSourceReadiness"] = product_name_field("DpmSourceReadiness")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ...,
        description="Portfolio identifier whose DPM source readiness was evaluated.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    )
    as_of_date: date = Field(
        ..., description="As-of date used for readiness evaluation.", examples=["2026-04-10"]
    )
    mandate_id: str | None = Field(
        None,
        description="Resolved mandate identifier when mandate binding was available.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    model_portfolio_id: str | None = Field(
        None,
        description="Resolved model portfolio identifier when model context was available.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    evaluated_instrument_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Instrument identifiers used for eligibility, tax-lot, and market-data readiness."
        ),
        examples=[["FO_EQ_AAPL_US", "FO_BOND_UST_2030"]],
    )
    families: list[DpmSourceFamilyReadiness] = Field(
        ..., description="Readiness row for each DPM source family."
    )
    supportability: DpmSourceReadinessSupportability = Field(
        ..., description="Overall source-family readiness supportability."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Core source lineage metadata for audit and downstream diagnostics.",
        examples=[{"source_system": "lotus-core", "contract_version": "rfc_087_v1"}],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetRow(BaseModel):
    instrument_id: str = Field(
        ...,
        description="Canonical instrument identifier in the model target universe.",
        examples=["EQ_US_AAPL"],
    )
    target_weight: Decimal = Field(
        ...,
        description="Target instrument weight as a decimal ratio between 0 and 1.",
        examples=["0.1200000000"],
    )
    min_weight: Decimal | None = Field(
        None,
        description="Optional minimum target band as a decimal ratio.",
        examples=["0.0800000000"],
    )
    max_weight: Decimal | None = Field(
        None,
        description="Optional maximum target band as a decimal ratio.",
        examples=["0.1600000000"],
    )
    target_status: str = Field(
        ...,
        description="Target lifecycle status from the model source system.",
        examples=["active"],
    )
    quality_status: str = Field(
        ...,
        description="Data quality status for this target row.",
        examples=["accepted"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["model_sg_balanced_202603_eq_us_aapl"],
    )

    model_config = ConfigDict()


class ModelPortfolioSupportability(BaseModel):
    state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = Field(
        ...,
        description="Supportability state for the resolved model target product.",
        examples=["READY"],
    )
    reason: str = Field(
        ...,
        description="Bounded reason code explaining model target readiness.",
        examples=["MODEL_TARGETS_READY"],
    )
    target_count: int = Field(
        ...,
        description="Number of target rows returned after request filtering.",
        examples=[7],
    )
    total_target_weight: Decimal = Field(
        ...,
        description="Sum of returned target weights as a decimal ratio.",
        examples=["1.0000000000"],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DpmModelPortfolioTarget"] = product_name_field("DpmModelPortfolioTarget")
    product_version: Literal["v1"] = product_version_field()
    model_portfolio_id: str = Field(
        ...,
        description="Canonical model portfolio identifier.",
        examples=["MODEL_SG_BALANCED_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version resolved for the as-of date.",
        examples=["2026.03"],
    )
    display_name: str = Field(
        ...,
        description="Business display name for the model portfolio.",
        examples=["Singapore Balanced DPM Model"],
    )
    base_currency: str = Field(..., description="Model base currency.", examples=["SGD"])
    risk_profile: str = Field(
        ...,
        description="Mandate risk profile aligned to this model.",
        examples=["balanced"],
    )
    mandate_type: str = Field(
        ...,
        description="Mandate type for which this model is approved.",
        examples=["discretionary"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Expected rebalance cadence.",
        examples=["monthly"],
    )
    approval_status: str = Field(
        ...,
        description="Approval lifecycle status for the resolved model version.",
        examples=["approved"],
    )
    approved_at: datetime | None = Field(
        None,
        description="Timestamp when the resolved model version was approved.",
        examples=["2026-03-20T09:00:00Z"],
    )
    effective_from: date = Field(
        ...,
        description="Resolved model version effective start date.",
        examples=["2026-03-25"],
    )
    effective_to: date | None = Field(
        None,
        description="Resolved model version effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    targets: list[ModelPortfolioTargetRow] = Field(
        ...,
        description="Deterministically ordered target rows for the resolved model version.",
    )
    supportability: ModelPortfolioSupportability = Field(
        ...,
        description="Readiness and completeness diagnostics for model target consumption.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage metadata for audit, replay, and downstream diagnostics.",
        examples=[
            {
                "source_system": "investment_office_model_system",
                "source_record_id": "model_sg_balanced_202603",
                "contract_version": "rfc_087_v1",
            }
        ],
    )

    model_config = ConfigDict()


class BenchmarkDefinitionRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve benchmark definition version.",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()


class BenchmarkCompositionWindowRequest(BaseModel):
    window: IntegrationWindow = Field(
        ...,
        description="Window used to resolve overlapping benchmark composition segments.",
    )

    model_config = ConfigDict()


class BenchmarkComponentResponse(BaseModel):
    index_id: str = Field(
        ...,
        description="Canonical index identifier used as a benchmark component.",
        examples=["IDX_MSCI_WORLD_TR"],
    )
    composition_weight: Decimal = Field(
        ...,
        description="Component weight effective for the benchmark composition.",
        examples=["0.6000000000"],
    )
    composition_effective_from: date = Field(
        ...,
        description="Composition effective start date.",
        examples=["2026-01-01"],
    )
    composition_effective_to: date | None = Field(
        None,
        description="Composition effective end date.",
        examples=["2026-03-31"],
    )
    rebalance_event_id: str | None = Field(
        None,
        description="Rebalance event identifier linking related composition changes.",
        examples=["rebalance_2026q1"],
    )

    model_config = ConfigDict()


class BenchmarkCompositionWindowResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["BenchmarkConstituentWindow"] = product_name_field(
        "BenchmarkConstituentWindow"
    )
    product_version: Literal["v1"] = product_version_field()
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    benchmark_currency: str = Field(
        ...,
        description="Benchmark currency enforced across the requested composition window.",
        examples=["USD"],
    )
    resolved_window: IntegrationWindow = Field(
        ...,
        description="Resolved date window returned by the composition contract.",
    )
    segments: list[BenchmarkComponentResponse] = Field(
        default_factory=list,
        description="Ordered benchmark composition segments overlapping the requested window.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata (contract_version, source_system, generated_by).",
        examples=[
            {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
                "generated_by": "query_control_plane_service",
            }
        ],
    )

    model_config = ConfigDict()


class BenchmarkDefinitionResponse(BaseModel):
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    benchmark_name: str = Field(
        ...,
        description="Display benchmark name.",
        examples=["Global Balanced 60/40 (TR)"],
    )
    benchmark_type: Literal["single_index", "composite"] = Field(
        ...,
        description="Benchmark composition type.",
        examples=["composite"],
    )
    benchmark_currency: str = Field(
        ...,
        description="Benchmark base/reporting currency.",
        examples=["USD"],
    )
    return_convention: Literal["price_return_index", "total_return_index"] = Field(
        ...,
        description="Benchmark return convention label.",
        examples=["total_return_index"],
    )
    benchmark_status: str = Field(
        ...,
        description="Benchmark lifecycle status.",
        examples=["active"],
    )
    benchmark_family: str | None = Field(
        None,
        description="Benchmark family grouping.",
        examples=["multi_asset_strategic"],
    )
    benchmark_provider: str | None = Field(
        None,
        description="Reference data provider for benchmark definition.",
        examples=["MSCI"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Rebalance cadence for composite benchmark definitions.",
        examples=["quarterly"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier applied to this benchmark.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Canonical benchmark classification labels (asset_class, sector, region, style)."
        ),
        examples=[{"asset_class": "multi_asset", "region": "global"}],
    )
    effective_from: date = Field(
        ...,
        description="Definition effective start date.",
        examples=["2025-01-01"],
    )
    effective_to: date | None = Field(
        None,
        description="Definition effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(
        ...,
        description="Data quality status for the resolved definition record.",
        examples=["accepted"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for resolved definition.",
        examples=["2026-01-31T08:00:00Z"],
    )
    source_vendor: str | None = Field(
        None,
        description="Source vendor identifier for definition lineage.",
        examples=["MSCI"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source vendor record identifier for deterministic replay.",
        examples=["bmk_60_40_v20260131"],
    )
    components: list[BenchmarkComponentResponse] = Field(
        default_factory=list,
        description="Effective benchmark component records for the requested as-of date.",
    )
    contract_version: str = Field(
        "rfc_062_v1",
        description="Query contract version for benchmark definition integration.",
        examples=["rfc_062_v1"],
    )

    model_config = ConfigDict()


class BenchmarkCatalogRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date for benchmark catalog retrieval.",
        examples=["2026-01-31"],
    )
    benchmark_type: str | None = Field(
        None,
        description="Optional benchmark type filter.",
        examples=["composite"],
    )
    benchmark_currency: str | None = Field(
        None,
        description="Optional benchmark currency filter.",
        examples=["USD"],
    )
    benchmark_status: str | None = Field(
        None,
        description="Optional benchmark status filter.",
        examples=["active"],
    )

    model_config = ConfigDict()


class BenchmarkCatalogResponse(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used for catalog resolution.",
        examples=["2026-01-31"],
    )
    records: list[BenchmarkDefinitionResponse] = Field(
        default_factory=list,
        description="Benchmark definition records effective for the requested date.",
        examples=[[{"benchmark_id": "BMK_GLOBAL_BALANCED_60_40", "benchmark_type": "composite"}]],
    )

    model_config = ConfigDict()


class IndexCatalogRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date for index catalog retrieval.",
        examples=["2026-01-31"],
    )
    index_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional targeted index identifiers to resolve. Use this when the caller already "
            "knows the component universe and needs canonical metadata without scanning the full "
            "effective catalog."
        ),
        examples=[["IDX_MSCI_WORLD_TR", "IDX_BLOOMBERG_GLOBAL_AGG_TR"]],
    )
    index_currency: str | None = Field(
        None,
        description="Optional index currency filter.",
        examples=["USD"],
    )
    index_type: str | None = Field(
        None,
        description="Optional index type filter.",
        examples=["equity_index"],
    )
    index_status: str | None = Field(
        None,
        description="Optional index status filter.",
        examples=["active"],
    )

    model_config = ConfigDict()


class IndexDefinitionResponse(BaseModel):
    index_id: str = Field(
        ..., description="Canonical index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    index_name: str = Field(
        ..., description="Display index name.", examples=["MSCI World Total Return"]
    )
    index_currency: str = Field(..., description="Index currency.", examples=["USD"])
    index_type: str | None = Field(
        None,
        description="Index type descriptor.",
        examples=["equity_index"],
    )
    index_status: str = Field(..., description="Index status.", examples=["active"])
    index_provider: str | None = Field(
        None,
        description="Index data provider.",
        examples=["MSCI"],
    )
    index_market: str | None = Field(
        None,
        description="Primary market or scope for index universe.",
        examples=["global_developed"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier applied to this index.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Canonical index classification labels required for attribution and benchmark "
            "exposure grouping. Broad benchmark component indices can carry governed "
            "broad-market sector labels rather than issuer sectors."
        ),
        examples=[{"asset_class": "equity", "sector": "broad_market_equity", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Definition effective end date.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(..., description="Data quality status.", examples=["accepted"])
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp.",
        examples=["2026-01-31T08:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor name.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for replay.",
        examples=["idx_world_tr_v20260131"],
    )

    model_config = ConfigDict()


class IndexCatalogResponse(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used for catalog resolution.",
        examples=["2026-01-31"],
    )
    records: list[IndexDefinitionResponse] = Field(
        default_factory=list,
        description="Index definition records effective for the requested date.",
        examples=[[{"index_id": "IDX_MSCI_WORLD_TR", "index_currency": "USD"}]],
    )

    model_config = ConfigDict()


class SeriesRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used for effective definition/composition resolution.",
        examples=["2026-01-31"],
    )
    window: IntegrationWindow = Field(
        ...,
        description="Date window for series extraction.",
    )
    frequency: Literal["daily"] = Field(
        ...,
        description="Requested output frequency label. Currently only daily is supported.",
        examples=["daily"],
    )

    model_config = ConfigDict()


class ReferencePageRequest(BaseModel):
    page_size: int = Field(
        250,
        ge=1,
        le=1000,
        description="Maximum number of component series records to return per page.",
        examples=[250],
    )
    page_token: str | None = Field(
        None,
        description="Opaque continuation token from a previous benchmark market-series page.",
        examples=["eyJwIjp7Imxhc3RfaW5kZXhfaWQiOiJJRFhfTVNDSSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class ReferencePageMetadata(BaseModel):
    page_size: int = Field(
        ...,
        description="Effective component page size used for this response.",
        examples=[250],
    )
    sort_key: str = Field(
        ...,
        description="Deterministic ordering applied to the paged component series.",
        examples=["index_id:asc"],
    )
    returned_component_count: int = Field(
        ...,
        description="Number of component series records returned in the current page.",
        examples=[250],
    )
    request_scope_fingerprint: str = Field(
        ...,
        description="Deterministic fingerprint of the request scope bound to this page sequence.",
        examples=["a6b8f6456a6d89cfcc1ce572f2cfcedb"],
    )
    next_page_token: str | None = Field(
        None,
        description=(
            "Opaque continuation token for the next page, null when no additional pages remain."
        ),
        examples=["eyJwIjp7Imxhc3RfaW5kZXhfaWQiOiJJRFhfTVNDSSJ9LCJzIjoiLi4uIn0="],
    )

    model_config = ConfigDict()


class BenchmarkMarketSeriesRequest(SeriesRequest):
    target_currency: str | None = Field(
        None,
        description="Optional target currency for response context and fx enrichment.",
        examples=["USD"],
    )
    series_fields: list[str] = Field(
        ...,
        description=(
            "Requested series fields. Supported: index_price, index_return, benchmark_return, "
            "component_weight, fx_rate."
        ),
        examples=[["index_price", "index_return", "component_weight"]],
    )
    page: ReferencePageRequest = Field(
        default_factory=ReferencePageRequest,
        description=(
            "Optional deterministic paging controls for large benchmark component universes."
        ),
    )

    model_config = ConfigDict()

    @model_validator(mode="after")
    def validate_series_fields(self):
        supported_fields = {
            "index_price",
            "index_return",
            "benchmark_return",
            "component_weight",
            "fx_rate",
        }
        requested_fields = [
            field.strip() for field in self.series_fields if field and field.strip()
        ]
        if not requested_fields:
            raise ValueError("series_fields must contain at least one supported value.")
        invalid = sorted({field for field in requested_fields if field not in supported_fields})
        if invalid:
            raise ValueError("Unsupported series_fields requested: " + ", ".join(invalid))
        if "fx_rate" in requested_fields and not self.target_currency:
            raise ValueError("target_currency is required when series_fields includes fx_rate.")
        self.series_fields = requested_fields
        return self


class SeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series point date.", examples=["2026-01-02"])
    series_currency: str | None = Field(
        None,
        description="Native component series currency for the returned price or return point.",
        examples=["USD"],
    )
    index_price: Decimal | None = Field(
        None,
        description="Index price value when requested.",
        examples=["4567.1234000000"],
    )
    index_return: Decimal | None = Field(
        None,
        description="Index return value when requested.",
        examples=["0.0023000000"],
    )
    benchmark_return: Decimal | None = Field(
        None,
        description="Vendor benchmark return value when requested.",
        examples=["0.0019000000"],
    )
    component_weight: Decimal | None = Field(
        None,
        description="Effective benchmark component weight for this point.",
        examples=["0.6000000000"],
    )
    fx_rate: Decimal | None = Field(
        None,
        description=(
            "Benchmark-currency to target-currency FX context rate when target "
            "currency is requested. This is not component-to-benchmark "
            "normalization."
        ),
        examples=["1.0842000000"],
    )
    quality_status: str | None = Field(
        None,
        description="Quality status for this point.",
        examples=["accepted"],
    )

    model_config = ConfigDict()


class ComponentSeriesResponse(BaseModel):
    index_id: str = Field(
        ..., description="Component index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    points: list[SeriesPoint] = Field(
        default_factory=list,
        description="Time series points for the requested component index.",
    )

    model_config = ConfigDict()


class BenchmarkMarketSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["MarketDataWindow"] = product_name_field("MarketDataWindow")
    product_version: Literal["v1"] = product_version_field()
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    as_of_date: date = Field(..., description="As-of date used for composition resolution.")
    benchmark_currency: str = Field(
        ...,
        description="Benchmark currency resolved for the requested benchmark context.",
        examples=["USD"],
    )
    target_currency: str | None = Field(
        None,
        description="Optional target currency requested by the caller for response context.",
        examples=["EUR"],
    )
    resolved_window: IntegrationWindow = Field(
        ..., description="Resolved window returned by query service."
    )
    frequency: str = Field(
        ..., description="Frequency label returned by the contract.", examples=["daily"]
    )
    component_series: list[ComponentSeriesResponse] = Field(
        default_factory=list,
        description="Component-level benchmark market series records.",
    )
    quality_status_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Aggregate quality status counts over all returned points.",
        examples=[{"accepted": 31, "estimated": 2}],
    )
    fx_context_source_currency: str | None = Field(
        None,
        description="Source currency for the optional FX context series returned in `fx_rate`.",
        examples=["USD"],
    )
    fx_context_target_currency: str | None = Field(
        None,
        description="Target currency for the optional FX context series returned in `fx_rate`.",
        examples=["EUR"],
    )
    normalization_policy: str = Field(
        ...,
        description=(
            "Contract policy label describing how downstream consumers should "
            "interpret the series. Current policy returns native component "
            "series and requires downstream benchmark-currency normalization."
        ),
        examples=["native_component_series_downstream_normalization_required"],
    )
    normalization_status: str = Field(
        ...,
        description=(
            "Status of the optional benchmark-to-target FX context attached to this response."
        ),
        examples=["native_component_series_with_benchmark_to_target_fx_context"],
    )
    component_metadata_policy: str = Field(
        ...,
        description=(
            "Contract guidance for resolving canonical component metadata such as "
            "classification labels. Benchmark market-series returns raw component series; use "
            "`POST /integration/indices/catalog` with targeted `index_ids` when canonical "
            "component metadata is required alongside these series."
        ),
        examples=["targeted_index_catalog_lookup_required_for_component_metadata"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the benchmark market-series scope.",
        examples=["a6b8f6456a6d89cfcc1ce572f2cfcedb"],
    )
    page: ReferencePageMetadata = Field(
        ...,
        description="Deterministic paging metadata for benchmark component series results.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata (contract_version, source_system, generated_by).",
        examples=[
            {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
                "generated_by": "query_control_plane_service",
            }
        ],
    )

    model_config = ConfigDict()


class IndexSeriesRequest(SeriesRequest):
    target_currency: str | None = Field(
        None,
        description="Optional target currency context for price series responses.",
        examples=["USD"],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesRequest(SeriesRequest):
    model_config = ConfigDict()


class RiskFreeSeriesRequest(SeriesRequest):
    currency: str = Field(
        ...,
        description="Series currency.",
        examples=["USD"],
    )
    series_mode: Literal["annualized_rate_series", "return_series"] = Field(
        ...,
        description="Risk-free series mode requested by downstream consumer.",
        examples=["annualized_rate_series"],
    )

    model_config = ConfigDict()


class IndexPriceSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_price: Decimal = Field(
        ..., description="Index price value.", examples=["4567.1234000000"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    value_convention: str = Field(
        ...,
        description="Value convention label for price series.",
        examples=["close_price"],
    )
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexReturnSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_return: Decimal = Field(..., description="Index return value.", examples=["0.0023000000"])
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class BenchmarkReturnSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    benchmark_return: Decimal = Field(
        ..., description="Benchmark return value.", examples=["0.0019000000"]
    )
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexPriceSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["IndexSeriesWindow"] = product_name_field("IndexSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    points: list[IndexPriceSeriesPoint] = Field(
        default_factory=list, description="Index price points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class IndexReturnSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["IndexSeriesWindow"] = product_name_field("IndexSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw index return series scope.",
        examples=["9ccdb0a1df40f0690241a5b52e9f1c1d"],
    )
    points: list[IndexReturnSeriesPoint] = Field(
        default_factory=list, description="Index return points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesResponse(BaseModel):
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw benchmark return series scope.",
        examples=["f4ea7426d13c0b95bbfd8d7d9dfb29af"],
    )
    points: list[BenchmarkReturnSeriesPoint] = Field(
        default_factory=list,
        description="Raw benchmark return points from upstream provider.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class RiskFreeSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    value: Decimal = Field(..., description="Risk-free series value.", examples=["0.0350000000"])
    value_convention: str = Field(
        ..., description="Value convention label.", examples=["annualized_rate"]
    )
    day_count_convention: str | None = Field(
        None,
        description="Day-count convention for annualized rate interpretation.",
        examples=["act_360"],
    )
    compounding_convention: str | None = Field(
        None,
        description="Compounding convention associated with rate series.",
        examples=["simple"],
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class RiskFreeSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["RiskFreeSeriesWindow"] = product_name_field("RiskFreeSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    currency: str = Field(..., description="Series currency code.", examples=["USD"])
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    series_mode: Literal["annualized_rate_series", "return_series"] = Field(
        ...,
        description="Series mode returned by the endpoint.",
        examples=["annualized_rate_series"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw risk-free series scope.",
        examples=["6dfc8591d95a53060efd94ddca9a266e"],
    )
    points: list[RiskFreeSeriesPoint] = Field(
        default_factory=list, description="Risk-free series points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for returned records.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class CoverageRequest(BaseModel):
    window: IntegrationWindow = Field(..., description="Coverage observation window.")

    model_config = ConfigDict()


class CoverageResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DataQualityCoverageReport"] = product_name_field(
        "DataQualityCoverageReport"
    )
    product_version: Literal["v1"] = product_version_field()
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the coverage diagnostics scope.",
        examples=["2cb014be96ad2cb65ce1833d9f2b88a2"],
    )
    observed_start_date: date | None = Field(
        None,
        description="Observed first date in data window.",
        examples=["2026-01-01"],
    )
    observed_end_date: date | None = Field(
        None,
        description="Observed last date in data window.",
        examples=["2026-01-31"],
    )
    expected_start_date: date = Field(
        ...,
        description="Expected start date from request window.",
        examples=["2026-01-01"],
    )
    expected_end_date: date = Field(
        ...,
        description="Expected end date from request window.",
        examples=["2026-01-31"],
    )
    total_points: int = Field(
        ...,
        description="Total points available in observed window.",
        examples=[31],
    )
    missing_dates_count: int = Field(
        ...,
        description="Count of missing calendar dates within expected window.",
        examples=[2],
    )
    missing_dates_sample: list[date] = Field(
        default_factory=list,
        description="Sample of missing dates in the expected window.",
        examples=[["2026-01-10", "2026-01-21"]],
    )
    quality_status_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Quality status distribution over observed points.",
        examples=[{"accepted": 29, "estimated": 2}],
    )

    model_config = ConfigDict()


class ClassificationTaxonomyRequest(BaseModel):
    as_of_date: date = Field(
        ..., description="As-of date for taxonomy resolution.", examples=["2026-01-31"]
    )
    taxonomy_scope: str | None = Field(
        None,
        description=(
            "Optional taxonomy scope filter such as `index`, `instrument`, or other "
            "governed source scopes. Omitting the field returns all effective scopes."
        ),
        examples=["index"],
    )

    model_config = ConfigDict()


class ClassificationTaxonomyEntry(BaseModel):
    classification_set_id: str = Field(
        ...,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    taxonomy_scope: str = Field(..., description="Taxonomy scope.", examples=["index"])
    dimension_name: str = Field(
        ..., description="Classification dimension name.", examples=["sector"]
    )
    dimension_value: str = Field(
        ..., description="Classification dimension value.", examples=["technology"]
    )
    dimension_description: str | None = Field(
        None,
        description="Human-readable dimension description.",
        examples=["Technology sector classification"],
    )
    effective_from: date = Field(..., description="Effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(
        None,
        description="Effective end date.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class ClassificationTaxonomyResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["InstrumentReferenceBundle"] = product_name_field(
        "InstrumentReferenceBundle"
    )
    product_version: Literal["v1"] = product_version_field()
    as_of_date: date = Field(
        ...,
        description="As-of date used for taxonomy response.",
        examples=["2026-01-31"],
    )
    records: list[ClassificationTaxonomyEntry] = Field(
        default_factory=list,
        description="Classification taxonomy entries effective on the requested date.",
        examples=[[{"classification_set_id": "wm_global_taxonomy_v1", "dimension_name": "sector"}]],
    )
    taxonomy_version: str = Field(
        "rfc_062_v1",
        description="Taxonomy contract version exposed by query service.",
        examples=["rfc_062_v1"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the taxonomy response scope.",
        examples=["d87368035df24ff9a42cb6e586e17ac7"],
    )

    model_config = ConfigDict()
