"""Persistence-independent evidence used to assess DPM source readiness."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ModelPortfolioDefinitionEvidence:
    """Approved model portfolio definition effective for an assessment date."""

    model_portfolio_id: str
    model_portfolio_version: str
    display_name: str
    base_currency: str
    risk_profile: str
    mandate_type: str
    rebalance_frequency: str | None
    approval_status: str
    approved_at: datetime | None
    effective_from: date
    effective_to: date | None
    source_system: str | None
    source_record_id: str | None
    observed_at: datetime | None
    quality_status: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ModelPortfolioTargetEvidence:
    """One instrument target in an approved model portfolio version."""

    instrument_id: str
    target_weight: Decimal
    min_weight: Decimal | None
    max_weight: Decimal | None
    target_status: str
    effective_from: date
    effective_to: date | None
    source_system: str | None
    source_record_id: str | None
    observed_at: datetime | None
    quality_status: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiscretionaryMandateBindingEvidence:
    """Effective discretionary authority and model binding for a portfolio."""

    portfolio_id: str
    mandate_id: str
    client_id: str
    mandate_type: str
    discretionary_authority_status: str
    booking_center_code: str
    jurisdiction_code: str
    model_portfolio_id: str
    policy_pack_id: str | None
    mandate_objective: str | None
    risk_profile: str
    investment_horizon: str
    review_cadence: str | None
    last_review_date: date | None
    next_review_due_date: date | None
    leverage_allowed: bool
    tax_awareness_allowed: bool
    settlement_awareness_required: bool
    rebalance_frequency: str
    rebalance_bands: Mapping[str, object]
    effective_from: date
    effective_to: date | None
    binding_version: int
    source_system: str | None
    source_record_id: str | None
    observed_at: datetime | None
    quality_status: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class InstrumentEligibilityEvidence:
    """Effective instrument shelf and dealing eligibility evidence."""

    security_id: str
    eligibility_status: str
    product_shelf_status: str
    buy_allowed: bool
    sell_allowed: bool
    restriction_reason_codes: tuple[str, ...]
    settlement_days: int
    settlement_calendar_id: str
    liquidity_tier: str | None
    issuer_id: str | None
    issuer_name: str | None
    ultimate_parent_issuer_id: str | None
    ultimate_parent_issuer_name: str | None
    asset_class: str | None
    country_of_risk: str | None
    effective_from: date
    effective_to: date | None
    eligibility_version: int
    source_system: str | None
    source_record_id: str | None
    observed_at: datetime | None
    quality_status: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class PortfolioTaxLotEvidence:
    """Position-lot state required for tax-aware DPM readiness."""

    portfolio_id: str
    security_id: str
    instrument_id: str
    lot_id: str
    open_quantity: Decimal
    original_quantity: Decimal
    acquisition_date: date
    lot_cost_base: Decimal
    lot_cost_local: Decimal
    source_transaction_id: str
    source_system: str | None
    calculation_policy_id: str | None
    calculation_policy_version: str | None
    local_currency: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class MarketPriceEvidence:
    """Latest instrument price selected no later than the assessment date."""

    security_id: str
    price_date: date
    price: Decimal
    currency: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class FxRateEvidence:
    """Latest currency-pair rate selected no later than the assessment date."""

    from_currency: str
    to_currency: str
    rate_date: date
    rate: Decimal
    created_at: datetime | None
    updated_at: datetime | None
