"""Application boundary for authoritative valuation-policy assignment resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from portfolio_common.domain.valuation import (
    PositionValuationPolicy,
    ResolvedValuationPolicyAssignment,
)


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeValuationPolicy:
    """Bind the selected source assignment to its exact executable policy."""

    assignment: ResolvedValuationPolicyAssignment
    policy: PositionValuationPolicy


class ValuationPolicyAssignmentResolver(Protocol):
    """Resolve one exact-scope, effective-dated valuation policy."""

    async def resolve(
        self,
        *,
        tenant_id: str,
        legal_book_id: str,
        security_id: str,
        valuation_date: date,
    ) -> ResolvedRuntimeValuationPolicy: ...
