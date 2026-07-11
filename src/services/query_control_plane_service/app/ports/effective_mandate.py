"""Source-read boundary for effective discretionary mandate identity."""

from datetime import date
from typing import Protocol

from ..domain.effective_mandate import EffectiveMandateBinding


class EffectiveMandateReader(Protocol):
    """Resolve a mandate binding without exposing persistence models."""

    async def resolve(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        mandate_id: str | None,
    ) -> EffectiveMandateBinding | None: ...
