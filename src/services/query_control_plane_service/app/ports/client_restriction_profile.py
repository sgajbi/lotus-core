"""Source-read boundary for effective client restriction resolution."""

from datetime import date
from typing import Protocol

from ..domain.client_restriction_profile import (
    ClientRestrictionSourceRecord,
)
from ..domain.effective_mandate import EffectiveMandateBinding


class ClientRestrictionProfileSourceReader(Protocol):
    """Read mandate and restriction evidence without exposing persistence models."""

    async def resolve_mandate_binding(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        mandate_id: str | None,
    ) -> EffectiveMandateBinding | None: ...

    async def list_restrictions(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_restrictions: bool,
    ) -> list[ClientRestrictionSourceRecord]: ...
