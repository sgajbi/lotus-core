"""SQLAlchemy adapter for authoritative valuation-policy assignment resolution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from portfolio_common.database_models import InstrumentValuationPolicyAssignmentRecord
from portfolio_common.domain.valuation import (
    InstrumentValuationPolicyAssignment,
    ValuationPolicyAssignmentStatus,
    resolve_position_valuation_policy,
    resolve_valuation_policy_assignment,
)
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..ports import (
    ResolvedRuntimeValuationPolicy,
    ValuationPolicyAuthorityKey,
    ValuationPolicyAuthorityRequest,
)

MAX_VALUATION_POLICY_AUTHORITY_REQUESTS = 500
VALUATION_POLICY_AUTHORITY_QUERY_CHUNK_SIZE = 100
_Value = TypeVar("_Value")


class SqlAlchemyValuationPolicyAssignmentResolver:
    """Resolve durable assignment history without loading obsolete source versions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve_many(
        self,
        requests: Sequence[ValuationPolicyAuthorityRequest],
    ) -> dict[ValuationPolicyAuthorityKey, ResolvedRuntimeValuationPolicy]:
        """Return one exact registered policy per deduplicated authority request."""

        if len(requests) > MAX_VALUATION_POLICY_AUTHORITY_REQUESTS:
            raise ValueError(
                "valuation-policy authority request batch exceeds "
                f"{MAX_VALUATION_POLICY_AUTHORITY_REQUESTS}"
            )
        request_by_key = {request.key: request for request in requests}
        if not request_by_key:
            return {}

        record = InstrumentValuationPolicyAssignmentRecord
        rows: list[InstrumentValuationPolicyAssignmentRecord] = []
        requested_scopes = list(dict.fromkeys(key[:3] for key in request_by_key))
        for scope_chunk in _chunks(
            requested_scopes,
            VALUATION_POLICY_AUTHORITY_QUERY_CHUNK_SIZE,
        ):
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
                    tuple_(
                        record.tenant_id,
                        record.legal_book_id,
                        record.security_id,
                    ).in_(scope_chunk)
                )
                .subquery()
            )
            latest_record = aliased(record, ranked_source_versions)
            statement = select(latest_record).where(
                ranked_source_versions.c.source_rank == 1,
            )
            rows.extend((await self._db.scalars(statement)).all())

        assignments_by_scope: dict[
            tuple[str, str, str],
            list[InstrumentValuationPolicyAssignment],
        ] = {}
        for row in rows:
            assignment = _assignment_from_record(row)
            assignments_by_scope.setdefault(assignment.scope_key, []).append(assignment)

        resolved: dict[ValuationPolicyAuthorityKey, ResolvedRuntimeValuationPolicy] = {}
        for key, request in request_by_key.items():
            assignment = resolve_valuation_policy_assignment(
                assignments_by_scope.get(request.scope.key, []),
                tenant_id=request.scope.tenant_id,
                legal_book_id=request.scope.legal_book_id,
                security_id=request.scope.security_id,
                valuation_date=request.valuation_date,
            )
            policy = resolve_position_valuation_policy(
                assignment.assignment.policy_id,
                assignment.assignment.policy_version,
            )
            resolved[key] = ResolvedRuntimeValuationPolicy(
                assignment=assignment,
                policy=policy,
            )
        return resolved


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


def _chunks(values: list[_Value], size: int) -> list[list[_Value]]:
    return [values[offset : offset + size] for offset in range(0, len(values), size)]
