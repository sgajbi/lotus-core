"""Independent immutable producer facts; no cash formula or eligibility policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from .calculation_lineage import canonical_content_hash, require_sha256_digest
from .financial.precision import EXACT_UNBOUNDED


class ObservationFamily(StrEnum):
    CASH_AVAILABILITY = "cash_availability"
    FUNDING_INVESTMENT = "funding_investment"


class ObservationCoverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class ObservationConflict(ValueError):
    """A source-safe refusal code, never producer-controlled diagnostic text."""


def require_observation_identity(value: str, field_name: str) -> None:
    """Require exact bounded source scope for facts and server submission grants."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{field_name} must be bounded canonical text")


@dataclass(frozen=True, slots=True)
class ObservationEnvelope:
    """Source business visibility and revision identity, independent of receipt time.

    Intervals are half-open. A missing upper bound means ongoing, not approved.
    Producer hashes are verified against the typed family payload by the writer.
    """

    tenant_id: str
    portfolio_id: str
    producer_id: str
    source_record_id: str
    source_revision: int
    source_cut_id: str
    definition_version: str
    effective_from: date
    effective_to: date | None
    observed_at: datetime
    generated_at: datetime
    coverage: ObservationCoverage
    coverage_scope: str
    predecessor_id: str | None = None
    expected_head_hash: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "tenant_id",
            "portfolio_id",
            "producer_id",
            "source_record_id",
            "source_cut_id",
            "definition_version",
            "coverage_scope",
        ):
            require_observation_identity(getattr(self, name), name)
        if type(self.source_revision) is not int or self.source_revision < 1:
            raise ValueError("source_revision must be a positive integer")
        if type(self.effective_from) is not date or (
            self.effective_to is not None and type(self.effective_to) is not date
        ):
            raise ValueError("effective bounds must be business dates")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective interval must be nonempty")
        for value in (self.observed_at, self.generated_at):
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError("observation timestamps must be timezone-aware")
        if self.generated_at < self.observed_at:
            raise ValueError("generation cannot precede observation")
        if not isinstance(self.coverage, ObservationCoverage):
            raise ValueError("coverage must use the governed vocabulary")
        if (self.predecessor_id is None) != (self.expected_head_hash is None):
            raise ValueError("correction requires predecessor and expected head hash together")
        if self.predecessor_id is not None:
            require_observation_identity(self.predecessor_id, "predecessor_id")
            if self.source_revision == 1:
                raise ValueError("original revision cannot name a predecessor")
        elif self.source_revision != 1:
            raise ValueError("later revisions must name a predecessor")
        if self.expected_head_hash is not None:
            require_sha256_digest(self.expected_head_hash, "expected_head_hash")

    @property
    def source_key(self) -> tuple[str, str, str, str]:
        return self.tenant_id, self.portfolio_id, self.producer_id, self.source_record_id

    def is_effective(self, business_date: date) -> bool:
        return self.effective_from <= business_date and (
            self.effective_to is None or business_date < self.effective_to
        )


def _canonical_cash_amount(value: Decimal, field_name: str) -> Decimal:
    """Match unconstrained PostgreSQL NUMERIC without unbounded exponent expansion."""
    exponent = value.as_tuple().exponent
    # Finite Decimal was required by the caller; NUMERIC supports 131072 integer
    # digits and 16383 fractional digits. Check compact metadata before formatting.
    if exponent < -16383 or (not value.is_zero() and value.adjusted() >= 131072):
        raise ValueError(f"{field_name} exceeds PostgreSQL NUMERIC representation limits")
    if value.is_zero():
        return Decimal((0, (0,), min(exponent, 0)))
    if exponent > 0:
        return Decimal(format(value, "f"))
    return value


@dataclass(frozen=True, slots=True)
class CashAvailabilityObservation:
    """Independent supplied amounts; unknown, observed zero and partial differ."""

    envelope: ObservationEnvelope
    currency: str
    settled: Decimal | None
    encumbered: Decimal | None
    available: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, ObservationEnvelope):
            raise TypeError("typed observation envelope required")
        if (
            not isinstance(self.currency, str)
            or len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isupper()
        ):
            raise ValueError("currency must be a canonical three-letter code")
        if not self.currency.isalpha():
            raise ValueError("currency must contain letters only")
        for name in ("settled", "encumbered", "available"):
            value = getattr(self, name)
            if value is not None:
                EXACT_UNBOUNDED.require_exact(value, field_name=name)
                object.__setattr__(self, name, _canonical_cash_amount(value, name))

    @property
    def family(self) -> ObservationFamily:
        return ObservationFamily.CASH_AVAILABILITY

    @property
    def content_hash(self) -> str:
        return _observation_hash(self, self.family)


@dataclass(frozen=True, slots=True)
class FundingInvestmentObservation:
    """Explicit producer assertions, not portfolio lifecycle or valuation proxies."""

    envelope: ObservationEnvelope
    funded: bool | None
    invested: bool | None

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, ObservationEnvelope):
            raise TypeError("typed observation envelope required")
        if any(
            value is not None and type(value) is not bool for value in (self.funded, self.invested)
        ):
            raise ValueError("funded/invested must be explicit booleans or unknown")

    @property
    def family(self) -> ObservationFamily:
        return ObservationFamily.FUNDING_INVESTMENT

    @property
    def content_hash(self) -> str:
        return _observation_hash(self, self.family)


PortfolioSourceObservation = CashAvailabilityObservation | FundingInvestmentObservation


def _observation_hash(observation: PortfolioSourceObservation, family: ObservationFamily) -> str:
    digest: str = canonical_content_hash(
        {
            "contract": "PortfolioFinancialSourceObservations:v1",
            "family": family.value,
            "observation": asdict(observation),
        }
    )
    return digest


def require_observation_hash(observation: PortfolioSourceObservation, supplied_hash: str) -> None:
    require_sha256_digest(supplied_hash, "content_hash")
    if observation.content_hash != supplied_hash:
        raise ObservationConflict("SOURCE_OBSERVATION_HASH_MISMATCH")


def require_successor(
    original: PortfolioSourceObservation,
    correction: PortfolioSourceObservation,
    *,
    original_id: str,
) -> None:
    """Validate a correction against the locked head, not a session-cached guess."""
    if (
        original.family != correction.family
        or original.envelope.source_key != correction.envelope.source_key
        or original.envelope.coverage_scope != correction.envelope.coverage_scope
        or (
            isinstance(original, CashAvailabilityObservation)
            and isinstance(correction, CashAvailabilityObservation)
            and original.currency != correction.currency
        )
    ):
        raise ObservationConflict("SOURCE_OBSERVATION_OWNER_MISMATCH")
    if (
        correction.envelope.predecessor_id != original_id
        or correction.envelope.expected_head_hash != original.content_hash
        or correction.envelope.source_revision != original.envelope.source_revision + 1
    ):
        raise ObservationConflict("SOURCE_OBSERVATION_STALE_HEAD")
