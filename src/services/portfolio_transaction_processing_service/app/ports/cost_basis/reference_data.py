"""Define the reference data required to calculate transaction cost basis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.tenant import TenantId


@dataclass(frozen=True, slots=True)
class CostBasisPortfolioReference:
    """Portfolio policy fields required by cost-basis processing."""

    portfolio_id: str
    base_currency: str
    cost_basis_method: CostBasisMethod
    tenant_id: str
    legal_book_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("portfolio_id", "base_currency"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a nonblank string")
            object.__setattr__(self, field_name, value.strip())
        if not isinstance(self.cost_basis_method, CostBasisMethod):
            raise TypeError("cost_basis_method must be a CostBasisMethod")
        object.__setattr__(self, "tenant_id", TenantId(self.tenant_id).value)
        if self.legal_book_id is not None:
            if not isinstance(self.legal_book_id, str) or not self.legal_book_id.strip():
                raise ValueError("legal_book_id must be a nonblank string when supplied")
            object.__setattr__(self, "legal_book_id", self.legal_book_id.strip())


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
