"""Transactional authority guard for valuation-policy assignment ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from portfolio_common.database_models import InstrumentValuationPolicyAssignmentRecord
from portfolio_common.domain.valuation.assignments import (
    InstrumentValuationPolicyAssignment,
    ValuationPolicyAssignmentError,
    ValuationPolicyAssignmentStatus,
    validate_no_overlapping_active_assignments,
)
from portfolio_common.domain.valuation.policy_registry import (
    UnknownValuationPolicyError,
    resolve_position_valuation_policy,
)
from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession


class ValuationPolicyAssignmentWriteGuard:
    """Serialize exact-scope writes and validate incoming records with durable history."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def validate(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return

        incoming = [_domain_from_mapping(record) for record in records]
        source_versions = [
            (*assignment.source_record_key, assignment.assignment_version)
            for assignment in incoming
        ]
        if len(source_versions) != len(set(source_versions)):
            raise ValuationPolicyAssignmentError(
                "valuation-policy assignment batch contains duplicate source versions"
            )
        for assignment in incoming:
            try:
                resolve_position_valuation_policy(
                    assignment.policy_id,
                    assignment.policy_version,
                )
            except UnknownValuationPolicyError as error:
                raise ValuationPolicyAssignmentError(str(error)) from error

        scopes = sorted({assignment.scope_key for assignment in incoming})
        for tenant_id, legal_book_id, security_id in scopes:
            lock_key = (
                f"instrument-valuation-policy-assignment:{tenant_id}:{legal_book_id}:{security_id}"
            )
            await self._db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": lock_key},
            )

        existing_rows = (
            await self._db.scalars(
                select(InstrumentValuationPolicyAssignmentRecord).where(
                    tuple_(
                        InstrumentValuationPolicyAssignmentRecord.tenant_id,
                        InstrumentValuationPolicyAssignmentRecord.legal_book_id,
                        InstrumentValuationPolicyAssignmentRecord.security_id,
                    ).in_(scopes)
                )
            )
        ).all()
        existing = [_domain_from_record(row) for row in existing_rows]
        validate_no_overlapping_active_assignments([*existing, *incoming])


def _domain_from_mapping(record: Mapping[str, Any]) -> InstrumentValuationPolicyAssignment:
    status = record["assignment_status"]
    return InstrumentValuationPolicyAssignment(
        tenant_id=record["tenant_id"],
        legal_book_id=record["legal_book_id"],
        security_id=record["security_id"],
        policy_id=record["policy_id"],
        policy_version=record["policy_version"],
        valid_from=record["valid_from"],
        valid_to=record.get("valid_to"),
        assignment_status=(
            status
            if isinstance(status, ValuationPolicyAssignmentStatus)
            else ValuationPolicyAssignmentStatus(status)
        ),
        assignment_version=record["assignment_version"],
        source_system=record["source_system"],
        source_record_id=record["source_record_id"],
        source_revision=record["source_revision"],
        observed_at=record["observed_at"],
        assignment_reason=record["assignment_reason"],
    )


def _domain_from_record(
    record: InstrumentValuationPolicyAssignmentRecord,
) -> InstrumentValuationPolicyAssignment:
    return _domain_from_mapping(
        {
            "tenant_id": record.tenant_id,
            "legal_book_id": record.legal_book_id,
            "security_id": record.security_id,
            "policy_id": record.policy_id,
            "policy_version": record.policy_version,
            "valid_from": record.valid_from,
            "valid_to": record.valid_to,
            "assignment_status": record.assignment_status,
            "assignment_version": record.assignment_version,
            "source_system": record.source_system,
            "source_record_id": record.source_record_id,
            "source_revision": record.source_revision,
            "observed_at": record.observed_at,
            "assignment_reason": record.assignment_reason,
        }
    )
