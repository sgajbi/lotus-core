"""Domain records required to resolve client tax-reference rules."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ClientTaxRuleSourceRecord:
    """Persistence-independent tax-rule evidence."""

    rule_set_id: str
    tax_year: int
    jurisdiction_code: str
    rule_code: str
    rule_category: str
    rule_status: str
    rule_source: str
    applies_to_asset_classes: tuple[str, ...]
    applies_to_security_ids: tuple[str, ...]
    applies_to_income_types: tuple[str, ...]
    rate: Decimal | None
    threshold_amount: Decimal | None
    threshold_currency: str | None
    effective_from: date
    effective_to: date | None
    rule_version: int
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
