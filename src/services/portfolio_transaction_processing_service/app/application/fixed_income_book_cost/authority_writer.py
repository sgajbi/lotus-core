"""Persist deterministic batches of lot amortized-cost source authority."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...domain.fixed_income_book_cost import (
    LotAmortizedCostPolicyAssignment,
)
from ...ports import (
    LotAmortizedCostAuthority,
    LotAmortizedCostAuthorityAppendOutcome,
    LotAmortizedCostAuthorityPort,
)


@dataclass(frozen=True, slots=True)
class PersistLotAmortizedCostAuthorityResult:
    """Batch write counts after deterministic duplicate classification."""

    submitted_count: int
    unique_count: int
    appended_count: int
    unchanged_count: int


class ConflictingLotAmortizedCostAuthorityBatchError(ValueError):
    """Raised before persistence when a batch reuses one source version inconsistently."""


class PersistLotAmortizedCostAuthorityUseCase:
    """Deduplicate, order, and persist an atomic caller-owned authority batch."""

    def __init__(self, authority: LotAmortizedCostAuthorityPort) -> None:
        self._authority = authority

    async def execute(
        self,
        authorities: Sequence[LotAmortizedCostAuthority],
    ) -> PersistLotAmortizedCostAuthorityResult:
        """Persist unique source versions in stable identity/version order."""

        unique = _deduplicate_authorities(authorities)
        appended_count = 0
        unchanged_count = 0
        for authority in sorted(unique.values(), key=_authority_order_key):
            outcome = await self._authority.append(authority)
            if outcome is LotAmortizedCostAuthorityAppendOutcome.APPENDED:
                appended_count += 1
            else:
                unchanged_count += 1
        return PersistLotAmortizedCostAuthorityResult(
            submitted_count=len(authorities),
            unique_count=len(unique),
            appended_count=appended_count,
            unchanged_count=unchanged_count,
        )


def _deduplicate_authorities(
    authorities: Sequence[LotAmortizedCostAuthority],
) -> dict[tuple[object, ...], LotAmortizedCostAuthority]:
    unique: dict[tuple[object, ...], LotAmortizedCostAuthority] = {}
    for authority in authorities:
        key = _authority_order_key(authority)
        existing = unique.get(key)
        if existing is not None and existing.content_hash() != authority.content_hash():
            raise ConflictingLotAmortizedCostAuthorityBatchError(
                "conflicting payloads share one amortized-cost source version"
            )
        unique[key] = authority
    return unique


def _authority_order_key(
    authority: LotAmortizedCostAuthority,
) -> tuple[object, ...]:
    if isinstance(authority, LotAmortizedCostPolicyAssignment):
        source_system = authority.source_system
        source_record_id = authority.source_record_id
        source_version = authority.assignment_version
    else:
        source_system = authority.source.source_system
        source_record_id = authority.source.source_record_id
        source_version = authority.source.fact_version
    return (
        *authority.scope.key,
        type(authority).__name__,
        source_system,
        source_record_id,
        source_version,
    )
