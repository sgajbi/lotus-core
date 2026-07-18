"""Domain records for portfolio-manager book membership."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from portfolio_common.domain.portfolio_party_roles import PortfolioPartyRoleType


@dataclass(frozen=True, slots=True)
class PortfolioManagerBookRecord:
    """Persistence-independent portfolio-master membership evidence."""

    portfolio_id: str
    client_id: str
    booking_center_code: str
    portfolio_type: str
    status: str
    open_date: date
    close_date: date | None
    base_currency: str
    created_at: datetime | None
    updated_at: datetime | None
    membership_source: Literal["party_role_assignment", "legacy_advisor_projection"] = (
        "legacy_advisor_projection"
    )
    role_type: PortfolioPartyRoleType | None = None
    source_system: str | None = None
    source_record_id: str | None = None
    observed_at: datetime | None = None
