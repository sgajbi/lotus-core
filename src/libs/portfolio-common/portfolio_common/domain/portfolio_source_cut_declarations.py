"""Strict source-cut identity and historical registry declarations; no authority inference."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum

from .calculation_lineage import canonical_content_hash, require_sha256_digest
from .portfolio_source_observations import require_observation_identity


class DeclaredCoverage(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class ClosedNeutralDeclaration:
    """Framework-independent marker for neutral declarations and their domain validators."""


def positive_revision(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError("positive exact revision required")


def ordered_dates(start: date, end: date, *, exclusive: bool = False) -> None:
    if (
        type(start) is not date
        or type(end) is not date
        or (start >= end if exclusive else start > end)
    ):
        raise ValueError("ordered explicit business dates required")


def require_currency(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 3
        or not value.isascii()
        or not value.isupper()
        or not value.isalpha()
    ):
        raise ValueError("explicit canonical currency required")


@dataclass(frozen=True, slots=True)
class EffectiveDeclaration(ClosedNeutralDeclaration):
    effective_from: date
    effective_to: date | None
    definition_version: str
    provenance_reference: str
    currency: str
    discretionary: bool | None
    included: bool

    def __post_init__(self) -> None:
        if type(self.effective_from) is not date:
            raise ValueError("explicit effective date required")
        if self.effective_to is not None:
            ordered_dates(self.effective_from, self.effective_to, exclusive=True)
        for value in (self.definition_version, self.provenance_reference):
            require_observation_identity(value, "declaration provenance")
        if (
            len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isupper()
            or not self.currency.isalpha()
        ):
            raise ValueError("explicit ISO-shaped currency required")
        if self.discretionary is not None and type(self.discretionary) is not bool:
            raise ValueError("discretionary must be explicit boolean or unknown")
        if type(self.included) is not bool:
            raise ValueError("explicit inclusion declaration required")


@dataclass(frozen=True, slots=True)
class HistoricalRegistryMember(ClosedNeutralDeclaration):
    source_member_id: str
    provider_namespace: str
    core_portfolio_id: str | None
    member_revision: int
    declarations: tuple[EffectiveDeclaration, ...]

    def __post_init__(self) -> None:
        for value in (self.source_member_id, self.provider_namespace):
            require_observation_identity(value, "member identity")
        if self.core_portfolio_id is not None:
            require_observation_identity(self.core_portfolio_id, "core_portfolio_id")
        positive_revision(self.member_revision)
        if type(self.declarations) is not tuple or not self.declarations:
            raise ValueError("immutable nonempty declaration history required")
        previous = None
        for declaration in self.declarations:
            if type(declaration) is not EffectiveDeclaration:
                raise ValueError("typed declaration required")
            EffectiveDeclaration.__post_init__(declaration)
            if previous is not None and (
                previous.effective_to is None or declaration.effective_from < previous.effective_to
            ):
                raise ValueError("ordered nonoverlapping half-open declarations required")
            previous = declaration

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(
            {"contract": "PortfolioHistoricalRegistryMember:v1", "member": asdict(self)}
        )


@dataclass(frozen=True, slots=True)
class SourceCutIdentity(ClosedNeutralDeclaration):
    tenant_id: str
    source_system: str
    scope_id: str
    source_cut_id: str
    revision: int
    definition_version: str
    coverage_from: date
    coverage_to: date
    calendar: str
    observed_at: datetime
    generated_at: datetime
    predecessor_hash: str | None
    expected_head_hash: str | None

    def __post_init__(self) -> None:
        for name in (
            "tenant_id",
            "source_system",
            "scope_id",
            "source_cut_id",
            "definition_version",
            "calendar",
        ):
            require_observation_identity(getattr(self, name), name)
        positive_revision(self.revision)
        ordered_dates(self.coverage_from, self.coverage_to)
        for stamp in (self.observed_at, self.generated_at):
            if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
                raise ValueError("aware source times required")
        for digest in (self.predecessor_hash, self.expected_head_hash):
            if digest is not None:
                require_sha256_digest(digest, "source head")
        if self.revision == 1:
            if self.predecessor_hash is not None or self.expected_head_hash is not None:
                raise ValueError("initial revision has no predecessor")
        elif self.predecessor_hash is None or self.predecessor_hash != self.expected_head_hash:
            raise ValueError("correction requires identical explicit predecessor and expected head")


@dataclass(frozen=True, slots=True)
class ExpectedPopulation(ClosedNeutralDeclaration):
    reference: str
    definition_version: str
    count: int
    content_hash: str

    def __post_init__(self) -> None:
        require_observation_identity(self.reference, "independent expected population")
        require_observation_identity(self.definition_version, "population definition")
        if type(self.count) is not int or self.count < 0:
            raise ValueError("exact nonnegative population count required")
        require_sha256_digest(self.content_hash, "expected population")


@dataclass(frozen=True, slots=True)
class HistoricalRegistryCut(ClosedNeutralDeclaration):
    identity: SourceCutIdentity
    expected_population: ExpectedPopulation
    declared_coverage: DeclaredCoverage
    supplied_count: int
    members_root: str
    chunk_count: int
    chunks_root: str

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not SourceCutIdentity
            or type(self.expected_population) is not ExpectedPopulation
        ):
            raise ValueError("typed source and independent population required")
        SourceCutIdentity.__post_init__(self.identity)
        ExpectedPopulation.__post_init__(self.expected_population)
        if not isinstance(self.declared_coverage, DeclaredCoverage):
            raise ValueError("explicit coverage required")
        if any(type(n) is not int or n < 0 for n in (self.supplied_count, self.chunk_count)):
            raise ValueError("exact nonnegative manifest counts required")
        for digest in (self.members_root, self.chunks_root):
            require_sha256_digest(digest, "registry manifest")
        if self.supplied_count > 0 and self.chunk_count == 0:
            raise ValueError("nonempty registry requires retained chunks")

    @property
    def population_verification(self) -> str:
        return "UNVERIFIED"

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(
            {"contract": "PortfolioHistoricalRegistry:v1", "cut": asdict(self)}
        )
