"""Source-read boundary for sustainability preference resolution."""

from datetime import date
from typing import Protocol

from ..domain.sustainability_preference_profile import SustainabilityPreferenceSourceRecord


class SustainabilityPreferenceProfileSourceReader(Protocol):
    """Read mandate and preference evidence without exposing persistence models."""

    async def list_preferences(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_preferences: bool,
    ) -> list[SustainabilityPreferenceSourceRecord]: ...
