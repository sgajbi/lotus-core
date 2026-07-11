"""Domain records required to resolve client tax-reference profiles."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ClientTaxProfileSourceRecord:
    """Persistence-independent tax-reference evidence."""

    tax_profile_id: str
    tax_residency_country: str
    booking_tax_jurisdiction: str
    tax_status: str
    profile_status: str
    withholding_tax_rate: Decimal | None
    capital_gains_tax_applicable: bool
    income_tax_applicable: bool
    treaty_codes: tuple[str, ...]
    eligible_account_types: tuple[str, ...]
    effective_from: date
    effective_to: date | None
    profile_version: int
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
