"""Source-read ports for DPM readiness evidence."""

from datetime import date
from typing import Protocol

from ..domain.dpm_source_readiness import (
    DiscretionaryMandateBindingEvidence,
    FxRateEvidence,
    InstrumentEligibilityEvidence,
    MarketPriceEvidence,
    ModelPortfolioDefinitionEvidence,
    ModelPortfolioTargetEvidence,
    PortfolioTaxLotEvidence,
)

DpmTaxLotPageKey = tuple[date, str]


class DpmReferenceDataReader(Protocol):
    """Read effective DPM reference evidence without exposing persistence models."""

    async def resolve_model_portfolio_definition(
        self,
        *,
        model_portfolio_id: str,
        as_of_date: date,
    ) -> ModelPortfolioDefinitionEvidence | None: ...

    async def list_model_portfolio_targets(
        self,
        *,
        model_portfolio_id: str,
        model_portfolio_version: str,
        as_of_date: date,
        include_inactive_targets: bool,
    ) -> list[ModelPortfolioTargetEvidence]: ...

    async def resolve_discretionary_mandate_binding(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        mandate_id: str | None,
        booking_center_code: str | None,
    ) -> DiscretionaryMandateBindingEvidence | None: ...

    async def list_instrument_eligibility_profiles(
        self,
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[InstrumentEligibilityEvidence]: ...

    async def list_latest_market_prices(
        self,
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> list[MarketPriceEvidence]: ...

    async def list_latest_fx_rates(
        self,
        *,
        currency_pairs: list[tuple[str, str]],
        as_of_date: date,
    ) -> list[FxRateEvidence]: ...


class DpmPortfolioStateReader(Protocol):
    """Read portfolio and tax-lot evidence for DPM readiness assessment."""

    async def portfolio_exists(self, portfolio_id: str) -> bool: ...

    async def list_portfolio_tax_lots(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        security_ids: list[str] | None,
        include_closed_lots: bool,
        lot_status_filter: str | None,
        after_sort_key: DpmTaxLotPageKey | None,
        limit: int,
    ) -> list[PortfolioTaxLotEvidence]: ...

    async def list_known_instrument_security_ids(self, security_ids: list[str]) -> set[str]: ...
