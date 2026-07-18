"""Read boundary for effective portfolio party-role assignments."""

from datetime import date
from typing import Protocol

from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)

from ..domain.portfolio_party_roles import PortfolioPartyRoleRecord


class PortfolioPartyRoleReader(Protocol):
    async def list_effective_assignments(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        party_id: str | None,
        role_types: tuple[PortfolioPartyRoleType, ...],
        role_scopes: tuple[PortfolioPartyRoleScope, ...],
        include_non_accepted: bool,
    ) -> list[PortfolioPartyRoleRecord]: ...
