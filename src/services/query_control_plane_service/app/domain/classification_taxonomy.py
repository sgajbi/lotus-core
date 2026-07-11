"""Persistence-independent classification taxonomy evidence."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ClassificationTaxonomyEvidence:
    """One effective governed classification label."""

    classification_set_id: str
    taxonomy_scope: str
    dimension_name: str
    dimension_value: str
    dimension_description: str | None
    effective_from: date
    effective_to: date | None
    quality_status: str
    observed_at: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
