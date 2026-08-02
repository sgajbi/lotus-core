"""Persistence boundary for immutable fixed-income book-cost profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from ...domain.fixed_income_book_cost import (
    LotAmortizedCostProfileVersion,
    LotBookCostAuthorityScope,
)


@dataclass(frozen=True, slots=True)
class LotAmortizedCostProfileHead:
    """Minimal current-version evidence used to plan correction materialization."""

    profile_id: str
    profile_version: int
    profile_content_hash: str
    authority_content_hash: str | None


class LotAmortizedCostProfileAppendOutcome(StrEnum):
    """Observable result of one immutable append attempt."""

    APPENDED = "APPENDED"
    UNCHANGED = "UNCHANGED"


class LotAmortizedCostProfilePort(Protocol):
    """Persist and query append-only lot amortized-cost profile versions."""

    async def acquire_materialization_lock(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> None:
        """Serialize source reload, version selection, and append for one source lot."""

        ...

    async def latest_head(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostProfileHead | None:
        """Return minimal evidence for the latest exact-scope profile version."""

        ...

    async def latest_verified_head(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostProfileHead | None:
        """Return the latest head only after verifying its complete persisted profile."""

        ...

    async def append(
        self,
        profile: LotAmortizedCostProfileVersion,
    ) -> LotAmortizedCostProfileAppendOutcome:
        """Append the next contiguous version or classify an exact retry as unchanged."""

        ...

    async def latest(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostProfileVersion | None:
        """Return the latest version for one exact tenant-safe source-lot scope."""

        ...

    async def effective_as_of(
        self,
        scope: LotBookCostAuthorityScope,
        *,
        effective_date: date,
    ) -> LotAmortizedCostProfileVersion | None:
        """Return the latest profile effective no later than the requested date."""

        ...
