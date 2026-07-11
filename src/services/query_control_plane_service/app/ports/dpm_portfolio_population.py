"""Read and continuation boundaries for DPM portfolio populations."""

from datetime import date
from typing import Any, Protocol

from ..domain.dpm_portfolio_population import (
    ApprovedModelPortfolio,
    DiscretionaryMandatePopulationMember,
)


class DpmPortfolioPopulationReader(Protocol):
    """Read approved models and effective mandates without exposing persistence models."""

    async def resolve_approved_model(
        self, *, model_portfolio_id: str, as_of_date: date
    ) -> ApprovedModelPortfolio | None: ...

    async def list_affected_mandates(
        self,
        *,
        model_portfolio_id: str,
        as_of_date: date,
        booking_center_code: str | None,
        include_inactive_mandates: bool,
    ) -> list[DiscretionaryMandatePopulationMember]: ...

    async def list_universe_candidates(
        self,
        *,
        as_of_date: date,
        booking_center_code: str | None,
        model_portfolio_ids: tuple[str, ...],
        include_inactive_mandates: bool,
        after_sort_key: tuple[str, str] | None,
        limit: int,
    ) -> list[DiscretionaryMandatePopulationMember]: ...


class DpmPopulationPageTokenCodec(Protocol):
    """Encode and decode opaque continuation state."""

    def encode(self, payload: dict[str, Any]) -> str: ...

    def decode(self, token: str | None) -> dict[str, Any]: ...
