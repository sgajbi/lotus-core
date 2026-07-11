"""Domain records for approved models and effective DPM mandate populations."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ApprovedModelPortfolio:
    """Approved model version effective for a business date."""

    model_portfolio_id: str
    model_portfolio_version: str
    approval_status: str
    approved_at: datetime | None
    effective_from: date
    effective_to: date | None
    source_system: str | None
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiscretionaryMandatePopulationMember:
    """Persistence-independent effective discretionary mandate binding."""

    portfolio_id: str
    mandate_id: str
    client_id: str
    booking_center_code: str
    jurisdiction_code: str
    discretionary_authority_status: str
    model_portfolio_id: str
    policy_pack_id: str | None
    mandate_objective: str | None
    risk_profile: str
    investment_horizon: str
    effective_from: date
    effective_to: date | None
    binding_version: int
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
