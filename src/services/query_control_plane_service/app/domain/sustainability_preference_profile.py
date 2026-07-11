"""Domain records required to resolve sustainability preferences."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SustainabilityPreferenceSourceRecord:
    """Persistence-independent sustainability preference evidence."""

    preference_framework: str
    preference_code: str
    preference_status: str
    preference_source: str
    minimum_allocation: Decimal | None
    maximum_allocation: Decimal | None
    applies_to_asset_classes: tuple[str, ...]
    exclusion_codes: tuple[str, ...]
    positive_tilt_codes: tuple[str, ...]
    effective_from: date
    effective_to: date | None
    preference_version: int
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
