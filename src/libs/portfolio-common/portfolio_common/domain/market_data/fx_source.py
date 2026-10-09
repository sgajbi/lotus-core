"""Bounded source revision and sealed-cut policy for the existing FX facility.

These values describe admitted facts, not institutional provider qualification.
The owning adapter supplies acceptance time; source observation time cannot replace it.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import (
    canonical_content_hash,
    require_sha256_digest,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.financial.precision import BOUNDED_18_10_EXACT

MAX_FX_CUT_MEMBERS = 512
MAX_FX_SOURCE_IDENTIFIER_LENGTH = 128


def require_fx_source_identifier(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_FX_SOURCE_IDENTIFIER_LENGTH
        or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value)
    ):
        raise ValueError("FX_SOURCE_IDENTIFIER_INVALID")


def _instant(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("FX_SOURCE_INSTANT_INVALID")


def _decimal_content(value: Decimal) -> str:
    # Exact storage bounds are checked before expansion, including compact exponents.
    BOUNDED_18_10_EXACT.require_exact(value, field_name="rate")
    if value <= 0:
        raise ValueError("FX_SOURCE_RATE_INVALID")
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


@dataclass(frozen=True)
class FxSourceScope:
    tenant_id: str
    provider_id: str
    source_id: str

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.provider_id, self.source_id):
            require_fx_source_identifier(value)

    def content(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "provider_id": self.provider_id,
            "source_id": self.source_id,
        }


@dataclass(frozen=True)
class FxSourceRevision:
    scope: FxSourceScope
    source_record_id: str
    source_revision: str
    from_currency: str
    to_currency: str
    rate_date: date
    rate: Decimal
    source_observed_at: datetime
    fixing_kind: str
    calendar_version: str
    predecessor_revision_id: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.source_record_id,
            self.source_revision,
            self.fixing_kind,
            self.calendar_version,
        ):
            require_fx_source_identifier(value)
        for value in (self.from_currency, self.to_currency):
            if normalize_currency_code(value) != value:
                raise ValueError("FX_SOURCE_CURRENCY_NOT_CANONICAL")
        if self.from_currency == self.to_currency:
            raise ValueError("FX_SOURCE_PAIR_INVALID")
        if type(self.rate_date) is not date:
            raise ValueError("FX_SOURCE_BUSINESS_DATE_INVALID")
        _instant(self.source_observed_at)
        _decimal_content(self.rate)
        if self.predecessor_revision_id is not None:
            require_sha256_digest(self.predecessor_revision_id, "predecessor_revision_id")
            if self.predecessor_revision_id == self.revision_id:
                raise ValueError("FX_SOURCE_SELF_PREDECESSOR")

    @property
    def revision_id(self) -> str:
        """Stable server identity: changed content at the same version must conflict."""
        return canonical_content_hash(
            {
                "schema": "fx_source_revision/v1",
                **self.scope.content(),
                "source_record_id": self.source_record_id,
                "source_revision": self.source_revision,
            }
        )

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(self.content())

    def content(self) -> dict[str, object]:
        return {
            "revision_id": self.revision_id,
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "rate_date": self.rate_date,
            "rate": _decimal_content(self.rate),
            "source_observed_at": self.source_observed_at,
            "fixing_kind": self.fixing_kind,
            "calendar_version": self.calendar_version,
            "predecessor_revision_id": self.predecessor_revision_id,
        }


def fx_cut_membership_hash(revisions: tuple[FxSourceRevision, ...]) -> str:
    return canonical_content_hash(
        {
            "schema": "fx_source_cut_members/v1",
            "members": sorted(
                ((revision.revision_id, revision.content_hash) for revision in revisions),
                key=lambda member: member[0],
            ),
        }
    )


@dataclass(frozen=True)
class FxSourceCut:
    scope: FxSourceScope
    source_cut_reference: str
    source_cut_revision: str
    source_observed_cutoff: datetime
    revisions: tuple[FxSourceRevision, ...]
    declared_member_count: int
    declared_membership_hash: str

    def __post_init__(self) -> None:
        require_fx_source_identifier(self.source_cut_reference)
        require_fx_source_identifier(self.source_cut_revision)
        _instant(self.source_observed_cutoff)
        require_sha256_digest(self.declared_membership_hash, "declared_membership_hash")
        if not isinstance(self.revisions, tuple):
            raise ValueError("FX_SOURCE_CUT_MEMBERS_NOT_IMMUTABLE")
        if not 1 <= len(self.revisions) <= MAX_FX_CUT_MEMBERS:
            raise ValueError("FX_SOURCE_CUT_SIZE_INVALID")
        if type(self.declared_member_count) is not int or self.declared_member_count != len(
            self.revisions
        ):
            raise ValueError("FX_SOURCE_CUT_MEMBER_COUNT_MISMATCH")
        if len({member.source_record_id for member in self.revisions}) != len(self.revisions):
            raise ValueError("FX_SOURCE_CUT_DUPLICATE_RECORD")
        if any(member.scope != self.scope for member in self.revisions):
            raise ValueError("FX_SOURCE_CUT_SCOPE_MISMATCH")
        if any(
            member.source_observed_at > self.source_observed_cutoff for member in self.revisions
        ):
            raise ValueError("FX_SOURCE_CUT_OBSERVATION_AFTER_CUTOFF")
        if fx_cut_membership_hash(self.revisions) != self.declared_membership_hash:
            raise ValueError("FX_SOURCE_CUT_CONTENT_MISMATCH")

    @property
    def cut_id(self) -> str:
        return canonical_content_hash(
            {
                "schema": "fx_source_cut/v1",
                **self.scope.content(),
                "source_cut_reference": self.source_cut_reference,
                "source_cut_revision": self.source_cut_revision,
            }
        )

    @property
    def content_hash(self) -> str:
        return canonical_content_hash(
            {
                "cut_id": self.cut_id,
                "source_observed_cutoff": self.source_observed_cutoff,
                "members": self.declared_membership_hash,
                "count": self.declared_member_count,
            }
        )


@dataclass(frozen=True)
class RetainedFxSourceCut:
    cut: FxSourceCut
    accepted_at: datetime

    def __post_init__(self) -> None:
        _instant(self.accepted_at)
        if self.accepted_at < self.cut.source_observed_cutoff:
            raise ValueError("FX_SOURCE_CUT_OBSERVATION_AFTER_ACCEPTANCE")

    def visible_at(self, *, source_as_of: datetime, known_as_of: datetime) -> bool:
        """Late backdated admission never becomes prior historical knowledge."""
        _instant(source_as_of)
        _instant(known_as_of)
        return self.cut.source_observed_cutoff <= source_as_of and self.accepted_at <= known_as_of
