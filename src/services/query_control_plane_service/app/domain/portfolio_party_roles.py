"""Persistence-independent portfolio party-role evidence."""

from dataclasses import dataclass
from datetime import date, datetime

from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)


@dataclass(frozen=True, slots=True)
class PortfolioPartyRoleRecord:
    portfolio_id: str
    party_id: str
    role_type: PortfolioPartyRoleType
    role_scope: PortfolioPartyRoleScope
    effective_from: date
    effective_to: date | None
    assignment_version: int
    source_system: str
    source_record_id: str
    observed_at: datetime
    quality_status: PortfolioPartyRoleQualityStatus
    created_at: datetime | None
    updated_at: datetime | None
