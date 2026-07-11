"""Persistence-independent index definition evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping


@dataclass(frozen=True, slots=True)
class IndexDefinitionEvidence:
    """One effective index master record."""

    index_id: str
    index_name: str
    index_currency: str
    index_type: str | None
    index_status: str
    index_provider: str | None
    index_market: str | None
    classification_set_id: str | None
    classification_labels: Mapping[str, str]
    effective_from: date
    effective_to: date | None
    quality_status: str
    source_timestamp: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
