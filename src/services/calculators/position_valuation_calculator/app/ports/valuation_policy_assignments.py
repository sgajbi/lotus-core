"""Application boundary for authoritative valuation-policy assignment resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from portfolio_common.domain.valuation import (
    PositionValuationPolicy,
    ResolvedValuationPolicyAssignment,
    ValuationAuthorityScope,
)

ValuationPolicyAuthorityKey = tuple[str, str, str, date]


@dataclass(frozen=True, slots=True)
class ValuationPolicyAuthorityRequest:
    """One exact-scope, effective-dated policy authority request."""

    scope: ValuationAuthorityScope
    valuation_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ValuationAuthorityScope):
            raise TypeError("scope must be a ValuationAuthorityScope")
        if type(self.valuation_date) is not date:
            raise TypeError("valuation_date must be an exact date")

    @property
    def key(self) -> ValuationPolicyAuthorityKey:
        return (*self.scope.key, self.valuation_date)


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeValuationPolicy:
    """Bind the selected source assignment to its exact executable policy."""

    assignment: ResolvedValuationPolicyAssignment
    policy: PositionValuationPolicy


class ValuationPolicyAssignmentResolver(Protocol):
    """Bulk-resolve exact-scope, effective-dated valuation policies."""

    async def resolve_many(
        self,
        requests: Sequence[ValuationPolicyAuthorityRequest],
    ) -> Mapping[ValuationPolicyAuthorityKey, ResolvedRuntimeValuationPolicy]: ...
