"""SQLAlchemy adapter for authoritative valuation-policy assignment resolution."""

from __future__ import annotations

from datetime import date

from portfolio_common.database_models import InstrumentValuationPolicyAssignmentRecord
from portfolio_common.domain.valuation import (
    InstrumentValuationPolicyAssignment,
    ValuationPolicyAssignmentStatus,
    resolve_position_valuation_policy,
    resolve_valuation_policy_assignment,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..ports import ResolvedRuntimeValuationPolicy


class SqlAlchemyValuationPolicyAssignmentResolver:
    """Resolve durable assignment history without loading obsolete source versions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(
        self,
        *,
        tenant_id: str,
        legal_book_id: str,
        security_id: str,
        valuation_date: date,
    ) -> ResolvedRuntimeValuationPolicy:
        """Return the sole active authority and exact registered policy for a date."""

        normalized_tenant_id = _required_identifier(tenant_id, "tenant_id")
        normalized_legal_book_id = _required_identifier(legal_book_id, "legal_book_id")
        normalized_security_id = _required_identifier(security_id, "security_id")

        record = InstrumentValuationPolicyAssignmentRecord
        source_rank = (
            func.row_number()
            .over(
                partition_by=(
                    record.tenant_id,
                    record.legal_book_id,
                    record.security_id,
                    record.source_system,
                    record.source_record_id,
                ),
                order_by=record.assignment_version.desc(),
            )
            .label("source_rank")
        )
        ranked_source_versions = (
            select(record, source_rank)
            .where(
                record.tenant_id == normalized_tenant_id,
                record.legal_book_id == normalized_legal_book_id,
                record.security_id == normalized_security_id,
            )
            .subquery()
        )
        latest_record = aliased(record, ranked_source_versions)
        statement = select(latest_record).where(
            ranked_source_versions.c.source_rank == 1,
            latest_record.assignment_status == ValuationPolicyAssignmentStatus.ACTIVE.value,
            latest_record.valid_from <= valuation_date,
            or_(latest_record.valid_to.is_(None), latest_record.valid_to >= valuation_date),
        )

        records = (await self._db.scalars(statement)).all()
        assignment = resolve_valuation_policy_assignment(
            [_assignment_from_record(item) for item in records],
            tenant_id=normalized_tenant_id,
            legal_book_id=normalized_legal_book_id,
            security_id=normalized_security_id,
            valuation_date=valuation_date,
        )
        policy = resolve_position_valuation_policy(
            assignment.assignment.policy_id,
            assignment.assignment.policy_version,
        )
        return ResolvedRuntimeValuationPolicy(assignment=assignment, policy=policy)


def _assignment_from_record(
    record: InstrumentValuationPolicyAssignmentRecord,
) -> InstrumentValuationPolicyAssignment:
    status = record.assignment_status
    return InstrumentValuationPolicyAssignment(
        tenant_id=record.tenant_id,
        legal_book_id=record.legal_book_id,
        security_id=record.security_id,
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        assignment_status=(
            status
            if isinstance(status, ValuationPolicyAssignmentStatus)
            else ValuationPolicyAssignmentStatus(status)
        ),
        assignment_version=record.assignment_version,
        source_system=record.source_system,
        source_record_id=record.source_record_id,
        source_revision=record.source_revision,
        observed_at=record.observed_at,
        assignment_reason=record.assignment_reason,
    )


def _required_identifier(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    return normalized
