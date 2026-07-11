"""Persistence-independent benchmark assignment evidence."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class BenchmarkAssignmentEvidence:
    """One effective portfolio-to-benchmark assignment selected for a business date."""

    portfolio_id: str
    benchmark_id: str
    effective_from: date
    effective_to: date | None
    assignment_source: str
    assignment_status: str
    policy_pack_id: str | None
    source_system: str | None
    assignment_recorded_at: datetime
    assignment_version: int
    created_at: datetime | None
    updated_at: datetime | None
