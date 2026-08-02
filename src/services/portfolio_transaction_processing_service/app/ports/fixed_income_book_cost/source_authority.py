"""Persistence boundary for source-owned fixed-income book-cost authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias

from ...domain.fixed_income_book_cost import (
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    LotEffectiveYieldFact,
)

LotAmortizedCostAuthority: TypeAlias = (
    LotAmortizedCostPolicyAssignment
    | LotAmortizedCostBasisFact
    | LotAmortizationScheduleFact
    | LotEffectiveYieldFact
)


@dataclass(frozen=True, slots=True)
class LotAmortizedCostAuthorityBundle:
    """All persisted authority candidates for one exact source-lot scope."""

    assignments: tuple[LotAmortizedCostPolicyAssignment, ...] = ()
    basis_facts: tuple[LotAmortizedCostBasisFact, ...] = ()
    schedule_facts: tuple[LotAmortizationScheduleFact, ...] = ()
    yield_facts: tuple[LotEffectiveYieldFact, ...] = ()


class LotAmortizedCostAuthorityAppendOutcome(StrEnum):
    """Observable outcome of one immutable source-version append."""

    APPENDED = "APPENDED"
    UNCHANGED = "UNCHANGED"


class LotAmortizedCostAuthorityPort(Protocol):
    """Append and load source-versioned amortized-cost authority."""

    async def append(
        self,
        authority: LotAmortizedCostAuthority,
    ) -> LotAmortizedCostAuthorityAppendOutcome:
        """Append new authority or classify an exact retry as unchanged."""

        ...

    async def load(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostAuthorityBundle:
        """Load all versions for deterministic domain resolution."""

        ...
