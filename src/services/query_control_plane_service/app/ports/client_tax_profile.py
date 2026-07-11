"""Source-read boundary for effective client tax-profile resolution."""

from datetime import date
from typing import Protocol

from ..domain.client_tax_profile import ClientTaxProfileSourceRecord


class ClientTaxProfileSourceReader(Protocol):
    """Read tax-reference evidence without exposing persistence models."""

    async def list_profiles(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_profiles: bool,
    ) -> list[ClientTaxProfileSourceRecord]: ...
