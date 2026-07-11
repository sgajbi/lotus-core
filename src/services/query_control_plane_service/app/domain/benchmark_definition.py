"""Persistence-independent benchmark definition evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping


@dataclass(frozen=True, slots=True)
class BenchmarkDefinitionEvidence:
    """One effective benchmark master record."""

    benchmark_id: str
    benchmark_name: str
    benchmark_type: str
    benchmark_currency: str
    return_convention: str
    benchmark_status: str
    benchmark_family: str | None
    benchmark_provider: str | None
    rebalance_frequency: str | None
    classification_set_id: str | None
    classification_labels: Mapping[str, str]
    effective_from: date
    effective_to: date | None
    source_timestamp: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    quality_status: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class BenchmarkComponentEvidence:
    """One effective constituent selected for a benchmark definition."""

    benchmark_id: str
    index_id: str
    composition_effective_from: date
    composition_effective_to: date | None
    composition_weight: Decimal
    rebalance_event_id: str | None
    source_timestamp: datetime | None
    source_vendor: str | None
    source_record_id: str | None
    quality_status: str
    created_at: datetime | None
    updated_at: datetime | None
