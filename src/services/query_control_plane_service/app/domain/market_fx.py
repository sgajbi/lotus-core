"""Persistence-independent dated FX rate evidence."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import require_sha256_digest
from portfolio_common.domain.market_data.fx_source import FxSourceScope


class FxSourceSelectionRejected(ValueError):
    """Stable source-safe selection refusal, never a fallback to global FX."""


@dataclass(frozen=True, slots=True)
class FxSourceSelection:
    scope: FxSourceScope
    source_as_of: datetime
    known_as_of: datetime
    cut_id: str | None = None

    def __post_init__(self) -> None:
        if self.source_as_of.utcoffset() is None or self.known_as_of.utcoffset() is None:
            raise FxSourceSelectionRejected("FX_SOURCE_SELECTION_INSTANT_INVALID")
        if self.cut_id is not None:
            require_sha256_digest(self.cut_id, "cut_id")


@dataclass(frozen=True, slots=True)
class FxRateSourceEvidence:
    scope: FxSourceScope
    revision_id: str
    content_hash: str
    source_observed_at: datetime
    accepted_at: datetime
    fixing_kind: str
    calendar_version: str
    cut_id: str

    def __post_init__(self) -> None:
        for name in ("revision_id", "content_hash", "cut_id"):
            require_sha256_digest(getattr(self, name), name)
        if (
            self.source_observed_at.utcoffset() is None
            or self.accepted_at.utcoffset() is None
            or self.source_observed_at > self.accepted_at
            or not self.fixing_kind
            or not self.calendar_version
        ):
            raise FxSourceSelectionRejected("FX_SOURCE_EVIDENCE_INVALID")

    def require_selection(self, selection: FxSourceSelection) -> None:
        if (
            self.scope != selection.scope
            or self.source_observed_at > selection.source_as_of
            or self.accepted_at > selection.known_as_of
            or selection.cut_id is not None
            and self.cut_id != selection.cut_id
        ):
            raise FxSourceSelectionRejected("FX_SOURCE_EVIDENCE_OUTSIDE_SELECTION")


@dataclass(frozen=True, slots=True)
class FxRateEvidence:
    """One dated rate; legacy rows have no qualified source provenance."""

    from_currency: str
    to_currency: str
    rate_date: date
    rate: Decimal
    created_at: datetime | None
    updated_at: datetime | None
    source: FxRateSourceEvidence | None = None
