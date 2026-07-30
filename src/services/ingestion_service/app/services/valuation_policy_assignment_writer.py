"""Append-only persistence boundary for valuation-policy assignments."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from portfolio_common.database_models import InstrumentValuationPolicyAssignmentRecord
from portfolio_common.domain.valuation.assignments import (
    InstrumentValuationPolicyAssignment,
    ValuationPolicyAssignmentError,
    ValuationPolicyAssignmentStatus,
    revaluation_start_for_assignment_correction,
    validate_no_overlapping_active_assignments,
)
from portfolio_common.domain.valuation.policy_registry import (
    UnknownValuationPolicyError,
    resolve_position_valuation_policy,
)
from portfolio_common.domain.valuation.source_versions import latest_source_versions
from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

AssignmentScopeKey = tuple[str, str, str]
AssignmentSourceKey = tuple[str, str, str, str, str]
AssignmentSourceVersionKey = tuple[str, str, str, str, str, int]
MAX_VALUATION_POLICY_ASSIGNMENT_WRITE_BATCH = 1000
VALUATION_POLICY_ASSIGNMENT_QUERY_CHUNK_SIZE = 100
_Value = TypeVar("_Value")


@dataclass(frozen=True, slots=True)
class ValuationPolicyAssignmentAuthorityChange:
    """Previous and accepted source versions plus bounded revaluation impact."""

    previous: InstrumentValuationPolicyAssignment | None
    accepted: InstrumentValuationPolicyAssignment

    @property
    def affected_from(self) -> date | None:
        """Return the earliest date whose valuation semantics may have changed."""

        if self.previous is None:
            if self.accepted.assignment_status is ValuationPolicyAssignmentStatus.ACTIVE:
                return self.accepted.valid_from
            return None
        return revaluation_start_for_assignment_correction(self.previous, self.accepted)


class ValuationPolicyAssignmentWriter:
    """Serialize assignment corrections and append only unambiguous source versions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def append_many(
        self,
        assignments: Sequence[InstrumentValuationPolicyAssignment],
    ) -> tuple[ValuationPolicyAssignmentAuthorityChange, ...]:
        """Append assignments and return exact old/new authority impact without committing."""

        if not assignments:
            return ()
        if len(assignments) > MAX_VALUATION_POLICY_ASSIGNMENT_WRITE_BATCH:
            raise ValuationPolicyAssignmentError(
                "valuation-policy assignment write batch exceeds "
                f"{MAX_VALUATION_POLICY_ASSIGNMENT_WRITE_BATCH}"
            )
        _reject_duplicate_source_versions(assignments)
        _validate_supported_policies(assignments)

        scopes = sorted({assignment.scope_key for assignment in assignments})
        await self._lock_scopes(scopes)
        durable_history = await self._load_histories(scopes)
        persisted_by_version = {
            _source_version_key(assignment): assignment for assignment in durable_history
        }
        pending: list[InstrumentValuationPolicyAssignment] = []
        for assignment in assignments:
            persisted = persisted_by_version.get(_source_version_key(assignment))
            if persisted is not None:
                if persisted != assignment:
                    raise ValuationPolicyAssignmentError(
                        "conflicting payloads share one source record and assignment_version"
                    )
                continue
            pending.append(assignment)
        if not pending:
            return ()

        latest_before_change = {
            assignment.source_record_key: assignment for assignment in _latest(durable_history)
        }
        pending.sort(
            key=lambda assignment: (*assignment.source_record_key, assignment.assignment_version)
        )
        changes: list[ValuationPolicyAssignmentAuthorityChange] = []
        for assignment in pending:
            previous = latest_before_change.get(assignment.source_record_key)
            if (
                previous is not None
                and assignment.assignment_version <= previous.assignment_version
            ):
                raise ValuationPolicyAssignmentError(
                    "valuation-policy assignment correction version must be newer than "
                    "existing source history"
                )
            changes.append(
                ValuationPolicyAssignmentAuthorityChange(
                    previous=previous,
                    accepted=assignment,
                )
            )
            latest_before_change[assignment.source_record_key] = assignment

        validate_no_overlapping_active_assignments([*durable_history, *pending])
        self._db.add_all([_record_from_assignment(assignment) for assignment in pending])
        await self._db.flush()
        return tuple(changes)

    async def _lock_scopes(self, scopes: Sequence[AssignmentScopeKey]) -> None:
        for tenant_id, legal_book_id, security_id in scopes:
            await self._db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {
                    "lock_key": (
                        "instrument-valuation-policy-assignment:"
                        f"{tenant_id}:{legal_book_id}:{security_id}"
                    )
                },
            )

    async def _load_histories(
        self,
        scopes: Sequence[AssignmentScopeKey],
    ) -> list[InstrumentValuationPolicyAssignment]:
        record = InstrumentValuationPolicyAssignmentRecord
        assignments: list[InstrumentValuationPolicyAssignment] = []
        for scope_chunk in _chunks(
            list(scopes),
            VALUATION_POLICY_ASSIGNMENT_QUERY_CHUNK_SIZE,
        ):
            rows = (
                await self._db.scalars(
                    select(record).where(
                        tuple_(
                            record.tenant_id,
                            record.legal_book_id,
                            record.security_id,
                        ).in_(scope_chunk)
                    )
                )
            ).all()
            assignments.extend(_assignment_from_record(row) for row in rows)
        return assignments


def _chunks(values: list[_Value], size: int) -> list[list[_Value]]:
    return [values[offset : offset + size] for offset in range(0, len(values), size)]


def _reject_duplicate_source_versions(
    assignments: Sequence[InstrumentValuationPolicyAssignment],
) -> None:
    identities = [_source_version_key(assignment) for assignment in assignments]
    if len(identities) != len(set(identities)):
        raise ValuationPolicyAssignmentError(
            "valuation-policy assignment batch contains duplicate source versions"
        )


def _validate_supported_policies(
    assignments: Iterable[InstrumentValuationPolicyAssignment],
) -> None:
    for assignment in assignments:
        try:
            resolve_position_valuation_policy(
                assignment.policy_id,
                assignment.policy_version,
            )
        except UnknownValuationPolicyError as error:
            raise ValuationPolicyAssignmentError(str(error)) from error


def _latest(
    assignments: Iterable[InstrumentValuationPolicyAssignment],
) -> list[InstrumentValuationPolicyAssignment]:
    latest: list[InstrumentValuationPolicyAssignment] = latest_source_versions(
        assignments,
        source_record_key=lambda assignment: assignment.source_record_key,
        source_version=lambda assignment: assignment.assignment_version,
        conflicting_version_error=lambda: ValuationPolicyAssignmentError(
            "conflicting payloads share one source record and assignment_version"
        ),
    )
    return latest


def _source_version_key(
    assignment: InstrumentValuationPolicyAssignment,
) -> AssignmentSourceVersionKey:
    return (*assignment.source_record_key, assignment.assignment_version)


def _record_from_assignment(
    assignment: InstrumentValuationPolicyAssignment,
) -> InstrumentValuationPolicyAssignmentRecord:
    return InstrumentValuationPolicyAssignmentRecord(
        tenant_id=assignment.tenant_id,
        legal_book_id=assignment.legal_book_id,
        security_id=assignment.security_id,
        policy_id=assignment.policy_id,
        policy_version=assignment.policy_version,
        valid_from=assignment.valid_from,
        valid_to=assignment.valid_to,
        assignment_status=assignment.assignment_status.value,
        assignment_version=assignment.assignment_version,
        source_system=assignment.source_system,
        source_record_id=assignment.source_record_id,
        source_revision=assignment.source_revision,
        observed_at=assignment.observed_at,
        assignment_reason=assignment.assignment_reason,
    )


def _assignment_from_record(
    record: InstrumentValuationPolicyAssignmentRecord,
) -> InstrumentValuationPolicyAssignment:
    return InstrumentValuationPolicyAssignment(
        tenant_id=record.tenant_id,
        legal_book_id=record.legal_book_id,
        security_id=record.security_id,
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        assignment_status=ValuationPolicyAssignmentStatus(record.assignment_status),
        assignment_version=record.assignment_version,
        source_system=record.source_system,
        source_record_id=record.source_record_id,
        source_revision=record.source_revision,
        observed_at=record.observed_at,
        assignment_reason=record.assignment_reason,
    )
