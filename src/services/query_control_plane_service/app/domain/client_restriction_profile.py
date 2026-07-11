"""Domain records required to resolve effective client restrictions."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ClientRestrictionSourceRecord:
    """Persistence-independent restriction evidence selected for the response."""

    restriction_scope: str
    restriction_code: str
    restriction_status: str
    restriction_source: str
    applies_to_buy: bool
    applies_to_sell: bool
    instrument_ids: tuple[str, ...]
    asset_classes: tuple[str, ...]
    issuer_ids: tuple[str, ...]
    country_codes: tuple[str, ...]
    effective_from: date
    effective_to: date | None
    restriction_version: int
    source_record_id: str | None
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
