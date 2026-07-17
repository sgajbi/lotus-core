"""Define the reference data required to calculate transaction cost basis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from portfolio_common.domain.cost_basis_method import CostBasisMethod


@dataclass(frozen=True, slots=True)
class CostBasisPortfolioReference:
    """Portfolio policy fields required by cost-basis processing."""

    portfolio_id: str
    base_currency: str
    cost_basis_method: CostBasisMethod


@dataclass(frozen=True, slots=True)
class CostBasisInstrumentReference:
    """Instrument classification fields required by cost-basis processing."""

    security_id: str
    product_type: str
    asset_class: str | None


@dataclass(frozen=True, slots=True)
class CostBasisReferenceData:
    """Portfolio policy and optional instrument facts loaded as one unit."""

    portfolio: CostBasisPortfolioReference
    instrument: CostBasisInstrumentReference | None


class CostBasisReferenceDataPort(Protocol):
    """Load the minimal portfolio and instrument facts needed by cost processing."""

    async def get_cost_basis_reference_data(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> CostBasisReferenceData | None: ...
