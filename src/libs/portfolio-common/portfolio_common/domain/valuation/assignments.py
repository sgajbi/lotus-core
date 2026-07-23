"""Effective-dated, tenant-safe instrument valuation-policy assignments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import cast

from ..calculation_lineage import canonical_content_hash
from .source_facts import ValuationAuthorityScope


class ValuationPolicyAssignmentError(ValueError):
    """Base error for unsupported assignment state."""


class MissingValuationPolicyAssignmentError(ValuationPolicyAssignmentError):
    """Raised when no authoritative assignment supports the requested scope and date."""


class OverlappingValuationPolicyAssignmentError(ValuationPolicyAssignmentError):
    """Raised when more than one source record claims authority for the same date."""


class ValuationPolicyAssignmentStatus(StrEnum):
    """Lifecycle state for an assignment source record."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class InstrumentValuationPolicyAssignment:
    """One versioned source assertion binding an instrument to a valuation policy."""

    tenant_id: str
    legal_book_id: str
    security_id: str
    policy_id: str
    policy_version: int
    valid_from: date
    valid_to: date | None
    assignment_status: ValuationPolicyAssignmentStatus
    assignment_version: int
    source_system: str
    source_record_id: str
    source_revision: str
    observed_at: datetime
    assignment_reason: str

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "legal_book_id",
            "security_id",
            "policy_id",
            "source_system",
            "source_record_id",
            "source_revision",
            "assignment_reason",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be nonblank")
        if self.policy_version < 1:
            raise ValueError("policy_version must be positive")
        if self.assignment_version < 1:
            raise ValueError("assignment_version must be positive")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

    @property
    def scope_key(self) -> tuple[str, str, str]:
        return self.authority_scope.key

    @property
    def authority_scope(self) -> ValuationAuthorityScope:
        """Return the exact normalized scope shared by assignments and source facts."""

        return ValuationAuthorityScope(
            tenant_id=self.tenant_id,
            legal_book_id=self.legal_book_id,
            security_id=self.security_id,
        )

    @property
    def source_record_key(self) -> tuple[str, str, str, str, str]:
        return (*self.scope_key, self.source_system.strip(), self.source_record_id.strip())

    def is_effective_on(self, valuation_date: date) -> bool:
        return self.valid_from <= valuation_date and (
            self.valid_to is None or self.valid_to >= valuation_date
        )

    def content_hash(self) -> str:
        """Return a deterministic hash for audit and cache invalidation evidence."""

        content_hash = canonical_content_hash(
            {
                "assignment_reason": self.assignment_reason.strip(),
                "assignment_status": self.assignment_status,
                "assignment_version": self.assignment_version,
                "legal_book_id": self.legal_book_id.strip(),
                "observed_at": self.observed_at,
                "policy_id": self.policy_id.strip(),
                "policy_version": self.policy_version,
                "security_id": self.security_id.strip(),
                "source_record_id": self.source_record_id.strip(),
                "source_revision": self.source_revision.strip(),
                "source_system": self.source_system.strip(),
                "tenant_id": self.tenant_id.strip(),
                "valid_from": self.valid_from,
                "valid_to": self.valid_to,
            }
        )
        return cast(str, content_hash)


@dataclass(frozen=True, slots=True)
class ValuationPolicyAssignmentCacheKey:
    """All assignment dimensions required for safe cached policy resolution."""

    tenant_id: str
    legal_book_id: str
    security_id: str
    valuation_date: date
    policy_id: str
    policy_version: int
    assignment_version: int
    source_revision: str
    assignment_content_hash: str


@dataclass(frozen=True, slots=True)
class ResolvedValuationPolicyAssignment:
    """Authoritative assignment plus deterministic cache identity."""

    assignment: InstrumentValuationPolicyAssignment
    cache_key: ValuationPolicyAssignmentCacheKey


def resolve_valuation_policy_assignment(
    assignments: list[InstrumentValuationPolicyAssignment],
    *,
    tenant_id: str,
    legal_book_id: str,
    security_id: str,
    valuation_date: date,
) -> ResolvedValuationPolicyAssignment:
    """Resolve one exact-scope assignment after ranking source versions first."""

    requested_scope = ValuationAuthorityScope(
        tenant_id=tenant_id,
        legal_book_id=legal_book_id,
        security_id=security_id,
    ).key
    scoped = [assignment for assignment in assignments if assignment.scope_key == requested_scope]
    latest = _latest_source_versions(scoped)
    effective = [
        assignment
        for assignment in latest
        if assignment.assignment_status is ValuationPolicyAssignmentStatus.ACTIVE
        and assignment.is_effective_on(valuation_date)
    ]
    if not effective:
        raise MissingValuationPolicyAssignmentError(
            "no active valuation-policy assignment for exact tenant, legal book, "
            "instrument, and date"
        )
    if len(effective) > 1:
        sources = sorted(
            f"{assignment.source_system.strip()}:{assignment.source_record_id.strip()}"
            for assignment in effective
        )
        raise OverlappingValuationPolicyAssignmentError(
            f"overlapping active valuation-policy assignments: {sources}"
        )

    assignment = effective[0]
    return ResolvedValuationPolicyAssignment(
        assignment=assignment,
        cache_key=ValuationPolicyAssignmentCacheKey(
            tenant_id=assignment.tenant_id.strip(),
            legal_book_id=assignment.legal_book_id.strip(),
            security_id=assignment.security_id.strip(),
            valuation_date=valuation_date,
            policy_id=assignment.policy_id.strip(),
            policy_version=assignment.policy_version,
            assignment_version=assignment.assignment_version,
            source_revision=assignment.source_revision.strip(),
            assignment_content_hash=assignment.content_hash(),
        ),
    )


def validate_no_overlapping_active_assignments(
    assignments: list[InstrumentValuationPolicyAssignment],
) -> None:
    """Reject overlapping authoritative windows after correction-version ranking."""

    latest = _latest_source_versions(assignments)
    active_by_scope: dict[tuple[str, str, str], list[InstrumentValuationPolicyAssignment]] = {}
    for assignment in latest:
        if assignment.assignment_status is ValuationPolicyAssignmentStatus.ACTIVE:
            active_by_scope.setdefault(assignment.scope_key, []).append(assignment)

    for scope, scoped_assignments in active_by_scope.items():
        ordered = sorted(
            scoped_assignments,
            key=lambda item: (
                item.valid_from,
                item.valid_to or date.max,
                item.source_system,
                item.source_record_id,
            ),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if previous.valid_to is None or current.valid_from <= previous.valid_to:
                raise OverlappingValuationPolicyAssignmentError(
                    "active valuation-policy assignment windows overlap for "
                    f"tenant={scope[0]}, legal_book={scope[1]}, security={scope[2]}"
                )


def revaluation_start_for_assignment_correction(
    previous: InstrumentValuationPolicyAssignment,
    current: InstrumentValuationPolicyAssignment,
) -> date | None:
    """Return the earliest bounded replay date when valuation semantics changed."""

    if previous.source_record_key != current.source_record_key:
        raise ValueError(
            "assignment correction must preserve exact scope and source record identity"
        )
    if current.assignment_version <= previous.assignment_version:
        raise ValueError("assignment correction version must increase")
    previous_semantics = (
        previous.policy_id.strip(),
        previous.policy_version,
        previous.valid_from,
        previous.valid_to,
        previous.assignment_status,
    )
    current_semantics = (
        current.policy_id.strip(),
        current.policy_version,
        current.valid_from,
        current.valid_to,
        current.assignment_status,
    )
    if current_semantics == previous_semantics:
        return None
    return min(previous.valid_from, current.valid_from)


def _latest_source_versions(
    assignments: list[InstrumentValuationPolicyAssignment],
) -> list[InstrumentValuationPolicyAssignment]:
    latest: dict[tuple[str, str, str, str, str], InstrumentValuationPolicyAssignment] = {}
    for assignment in assignments:
        existing = latest.get(assignment.source_record_key)
        if existing is None or assignment.assignment_version > existing.assignment_version:
            latest[assignment.source_record_key] = assignment
        elif (
            assignment.assignment_version == existing.assignment_version and assignment != existing
        ):
            raise ValuationPolicyAssignmentError(
                "conflicting payloads share one source record and assignment_version"
            )
    return list(latest.values())
