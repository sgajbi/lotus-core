from __future__ import annotations

from datetime import date
from typing import Protocol

from ..read_models import PortfolioTaxLotReadRecord


class PortfolioTaxLotReader(Protocol):
    async def portfolio_exists(self, portfolio_id: str) -> bool: ...

    async def list_portfolio_tax_lots(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        security_ids: list[str] | None,
        include_closed_lots: bool,
        lot_status_filter: str | None,
        after_sort_key: tuple[date, str] | None,
        limit: int,
    ) -> list[PortfolioTaxLotReadRecord]: ...

    async def list_known_instrument_security_ids(self, security_ids: list[str]) -> set[str]: ...
