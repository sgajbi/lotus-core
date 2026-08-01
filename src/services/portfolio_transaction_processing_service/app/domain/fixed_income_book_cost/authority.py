"""Exact-scope authority for lot-level amortized-cost policy assignment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)
from portfolio_common.domain.source_versions import latest_source_versions


class AmortizedCostAuthorityError(ValueError):
    """Base error for unsupported amortized-cost authority state."""


class MissingAmortizedCostAssignmentError(AmortizedCostAuthorityError):
    """Raised when no exact-scope policy assignment supports the requested date."""


class OverlappingAmortizedCostAssignmentError(AmortizedCostAuthorityError):
    """Raised when multiple authoritative assignments claim the same lot and date."""


class AmortizedCostAssignmentStatus(StrEnum):
    """Lifecycle state of one source-owned assignment record."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class LotBookCostAuthorityScope:
    """Tenant-safe identity of one source lot inside its legal portfolio book."""

    tenant_id: str
    legal_book_id: str
    portfolio_id: str
    security_id: str
    lot_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "security_id",
            "lot_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        """Return the normalized exact-scope identity."""

        return (
            self.tenant_id,
            self.legal_book_id,
            self.portfolio_id,
            self.security_id,
            self.lot_id,
        )


@dataclass(frozen=True, slots=True)
class LotAmortizedCostPolicyAssignment:
    """One effective-dated source assertion assigning a policy to a source lot."""

    scope: LotBookCostAuthorityScope
    policy_id: str
    policy_version: int
    valid_from: date
    valid_to: date | None
    assignment_status: AmortizedCostAssignmentStatus
    assignment_version: int
    source_system: str
    source_record_id: str
    source_revision: str
    observed_at: datetime
    assignment_reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, LotBookCostAuthorityScope):
            raise TypeError("scope must be a LotBookCostAuthorityScope")
        for field_name in (
            "policy_id",
            "source_system",
            "source_record_id",
            "source_revision",
            "assignment_reason",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        _require_positive_integer(self.policy_version, "policy_version")
        _require_positive_integer(self.assignment_version, "assignment_version")
        if type(self.valid_from) is not date:
            raise TypeError("valid_from must be a date")
        if self.valid_to is not None and type(self.valid_to) is not date:
            raise TypeError("valid_to must be a date or None")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        if not isinstance(self.assignment_status, AmortizedCostAssignmentStatus):
            raise TypeError("assignment_status must be an AmortizedCostAssignmentStatus")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

    @property
    def source_record_key(self) -> tuple[str, str, str, str, str, str, str]:
        """Return immutable correction identity within the exact authority scope."""

        return (*self.scope.key, self.source_system, self.source_record_id)

    def is_effective_on(self, effective_date: date) -> bool:
        """Return whether this assignment claims the requested date."""

        if type(effective_date) is not date:
            raise TypeError("effective_date must be a date")
        return self.valid_from <= effective_date and (
            self.valid_to is None or self.valid_to >= effective_date
        )

    def content_hash(self) -> str:
        """Bind exact scope, policy semantics, lifecycle, and source evidence."""

        return cast(
            str,
            canonical_content_hash(
                {
                    "assignment_reason": self.assignment_reason,
                    "assignment_status": self.assignment_status,
                    "assignment_version": self.assignment_version,
                    "observed_at": self.observed_at,
                    "policy_id": self.policy_id,
                    "policy_version": self.policy_version,
                    "scope": {
                        "legal_book_id": self.scope.legal_book_id,
                        "lot_id": self.scope.lot_id,
                        "portfolio_id": self.scope.portfolio_id,
                        "security_id": self.scope.security_id,
                        "tenant_id": self.scope.tenant_id,
                    },
                    "source_record_id": self.source_record_id,
                    "source_revision": self.source_revision,
                    "source_system": self.source_system,
                    "valid_from": self.valid_from,
                    "valid_to": self.valid_to,
                }
            ),
        )

    def source_reference(self) -> FinancialSourceReference:
        """Return normalized immutable evidence for downstream calculation lineage."""

        return FinancialSourceReference(
            source_system=self.source_system,
            source_record_id=self.source_record_id,
            source_revision=self.source_revision,
            source_content_hash=self.content_hash(),
            observed_at=self.observed_at,
        )


@dataclass(frozen=True, slots=True)
class AmortizedCostAssignmentCacheKey:
    """Complete identity required for safe assignment-resolution caching."""

    scope: LotBookCostAuthorityScope
    effective_date: date
    policy_id: str
    policy_version: int
    assignment_version: int
    source_revision: str
    assignment_content_hash: str


@dataclass(frozen=True, slots=True)
class ResolvedAmortizedCostAssignment:
    """One authoritative assignment and its deterministic cache identity."""

    assignment: LotAmortizedCostPolicyAssignment
    cache_key: AmortizedCostAssignmentCacheKey


def resolve_amortized_cost_assignment(
    assignments: list[LotAmortizedCostPolicyAssignment],
    *,
    scope: LotBookCostAuthorityScope,
    effective_date: date,
) -> ResolvedAmortizedCostAssignment:
    """Resolve one latest, active, exact-scope assignment without fallback."""

    if not isinstance(scope, LotBookCostAuthorityScope):
        raise TypeError("scope must be a LotBookCostAuthorityScope")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date")
    scoped = [assignment for assignment in assignments if assignment.scope == scope]
    latest = _latest_assignments(scoped)
    effective = [
        assignment
        for assignment in latest
        if assignment.assignment_status is AmortizedCostAssignmentStatus.ACTIVE
        and assignment.is_effective_on(effective_date)
    ]
    if not effective:
        raise MissingAmortizedCostAssignmentError(
            "no active amortized-cost assignment for exact tenant, legal book, "
            "portfolio, security, source lot, and date"
        )
    if len(effective) > 1:
        sources = sorted(
            f"{assignment.source_system}:{assignment.source_record_id}" for assignment in effective
        )
        raise OverlappingAmortizedCostAssignmentError(
            f"overlapping active amortized-cost assignments: {sources}"
        )
    assignment = effective[0]
    return ResolvedAmortizedCostAssignment(
        assignment=assignment,
        cache_key=AmortizedCostAssignmentCacheKey(
            scope=assignment.scope,
            effective_date=effective_date,
            policy_id=assignment.policy_id,
            policy_version=assignment.policy_version,
            assignment_version=assignment.assignment_version,
            source_revision=assignment.source_revision,
            assignment_content_hash=assignment.content_hash(),
        ),
    )


def validate_no_overlapping_active_amortized_cost_assignments(
    assignments: list[LotAmortizedCostPolicyAssignment],
) -> None:
    """Reject overlapping active windows after source-correction ranking."""

    active_by_scope: dict[
        tuple[str, str, str, str, str], list[LotAmortizedCostPolicyAssignment]
    ] = {}
    for assignment in _latest_assignments(assignments):
        if assignment.assignment_status is AmortizedCostAssignmentStatus.ACTIVE:
            active_by_scope.setdefault(assignment.scope.key, []).append(assignment)
    for scope_key, scoped in active_by_scope.items():
        ordered = sorted(
            scoped,
            key=lambda assignment: (
                assignment.valid_from,
                assignment.valid_to or date.max,
                assignment.source_system,
                assignment.source_record_id,
            ),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if previous.valid_to is None or current.valid_from <= previous.valid_to:
                raise OverlappingAmortizedCostAssignmentError(
                    f"active amortized-cost assignment windows overlap for scope={scope_key}"
                )


def amortization_replay_start_for_assignment_correction(
    previous: LotAmortizedCostPolicyAssignment,
    current: LotAmortizedCostPolicyAssignment,
) -> date | None:
    """Return the earliest bounded replay date when assignment semantics changed."""

    if previous.source_record_key != current.source_record_key:
        raise ValueError(
            "assignment correction must preserve exact scope and source record identity"
        )
    if current.assignment_version <= previous.assignment_version:
        raise ValueError("assignment correction version must increase")
    previous_semantics = (
        previous.policy_id,
        previous.policy_version,
        previous.valid_from,
        previous.valid_to,
        previous.assignment_status,
    )
    current_semantics = (
        current.policy_id,
        current.policy_version,
        current.valid_from,
        current.valid_to,
        current.assignment_status,
    )
    if current_semantics == previous_semantics:
        return None
    return min(previous.valid_from, current.valid_from)


def _latest_assignments(
    assignments: list[LotAmortizedCostPolicyAssignment],
) -> list[LotAmortizedCostPolicyAssignment]:
    return cast(
        list[LotAmortizedCostPolicyAssignment],
        latest_source_versions(
            assignments,
            source_record_key=lambda assignment: assignment.source_record_key,
            source_version=lambda assignment: assignment.assignment_version,
            conflicting_version_error=lambda: AmortizedCostAuthorityError(
                "conflicting payloads share one source record and assignment_version"
            ),
        ),
    )


def _require_positive_integer(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
